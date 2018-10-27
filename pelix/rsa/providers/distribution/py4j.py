#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Py4j-based Distribution and Discovery Provider

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Thread, RLock
import logging

from osgiservicebridge.bridge import (
    JavaServiceProxy,
    Py4jServiceBridgeEventListener,
    Py4jServiceBridge,
    PythonService,
)
from osgiservicebridge.protobuf import (
    ProtobufJavaServiceProxy,
    ProtobufPythonService,
)

from py4j.java_gateway import GatewayParameters, CallbackServerParameters
from py4j.java_gateway import DEFAULT_PORT, DEFAULT_PYTHON_PROXY_PORT

# needed ipopo decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Instantiate,
    Property,
    Validate,
    ValidateComponent,
    Invalidate,
    PostRegistration,
)

from pelix.ipopo.constants import (
    ARG_BUNDLE_CONTEXT,
    ARG_PROPERTIES,
)

# Providers API
from pelix.rsa import prop_dot_suffix
from pelix.rsa.providers.distribution import (
    Container,
    ExportContainer,
    ImportContainer,
    DistributionProvider,
    SERVICE_EXPORT_CONTAINER,
    SERVICE_IMPORT_CONTAINER,
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER,
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER,
)
from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Note:  These must match the Java-side constants recored in Java interface
# class: org.eclipse.ecf.provider.py4j.Py4jConstants
ECF_PY4J_CONTAINER_CONFIG_TYPE = "ecf.py4j"
ECF_PY4J_NAMESPACE = "ecf.namespace.py4j"

ECF_PY4J_JAVA_HOST_CONFIG_TYPE = "ecf.py4j.host"
ECF_PY4J_JAVA_CONSUMER_CONFIG_TYPE = "ecf.py4j.consumer"
ECF_PY4J_PYTHON_HOST_CONFIG_TYPE = "ecf.py4j.host.python"
ECF_PY4J_PYTHON_CONSUMER_CONFIG_TYPE = "ecf.py4j.consumer.python"
ECF_PY4J_SUPPORTED_INTENTS = [
    "exactlyOnce",
    "passByReference",
    "ordered",
    "py4j",
    "py4j.async",
    "osgi.async",
    "osgi.private",
]
# Protobuf
ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE = "ecf.py4j.protobuf.host"
ECF_PY4JPB_JAVA_CONSUMER_CONFIG_TYPE = "ecf.py4j.protobuf.consumer"
ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE = "ecf.py4j.python.protobuf.host"
ECF_PY4JPB_PYTHON_CONSUMER_CONFIG_TYPE = "ecf.py4j.python.protobuf.consumer"
ECF_PY4JPB_SUPPORTED_INTENTS = [
    "exactlyOnce",
    "passByReference",
    "passByValue",
    "ordered",
    "py4j",
    "py4j.protobuf",
    "py4j.async",
    "osgi.async",
    "osgi.private",
]

ECF_PY4J_JAVA_PORT_PROP = "javaport"
ECF_PY4J_PYTHON_PORT_PROP = "pythonport"
ECF_PY4J_DEFAULT_SERVICE_TIMEOUT = "defaultservicetimeout"

# ------------------------------------------------------------------------------


@ComponentFactory(ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Provides([SERVICE_EXPORT_CONTAINER, SERVICE_IMPORT_CONTAINER])
class Py4jContainer(ExportContainer, ImportContainer):
    def __init__(self, max_workers=5):
        ExportContainer.__init__(self)
        ImportContainer.__init__(self)
        self._max_workers = max_workers
        self._executor = None

    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context, container_props):
        Container._validate_component(self, bundle_context, container_props)
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    @Invalidate
    def _invalidate_component(self, _):
        Container._invalidate_component(self, _)
        if self._executor:
            self._executor.shutdown()
            self._executor = None

    def get_connected_id(self):
        return ExportContainer.get_connected_id(self)

    def _export_service(self, svc, ed):
        # pylint: disable=W0212
        # modify svc class to have appropriate metadata for py4j
        timeout = ed.get_osgi_basic_timeout()
        if not timeout:
            timeout = 30

        args = [
            self._get_distribution_provider()._get_bridge(),
            ed.get_interfaces(),
            svc,
            self._executor,
            timeout,
        ]

        if (
            ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE
            in ed.get_remote_configs_supported()
        ):
            clazz = ProtobufPythonService
        else:
            clazz = PythonService

        psvc = clazz(*args)

        self._get_distribution_provider()._get_bridge().export(
            psvc, ed.get_properties()
        )
        ExportContainer._export_service(self, psvc, ed)
        return True

    def _unexport_service(self, ed):
        # pylint: disable=W0212
        dp = self._get_distribution_provider()
        if dp:
            bridge = dp._get_bridge()
            if bridge:
                bridge.unexport(ed.get_id())
        ExportContainer._unexport_service(self, ed)
        return True

    def _prepare_proxy(self, endpoint_description):
        # pylint: disable=W0212
        # lookup the bridge proxy associated with the
        # endpoint_description.get_id()
        bridge = self._get_distribution_provider()._get_bridge()
        proxy = bridge.get_import_endpoint(endpoint_description.get_id())[0]
        timeout = endpoint_description.get_osgi_basic_timeout()
        if not timeout:
            timeout = self._container_props.get(
                ECF_PY4J_DEFAULT_SERVICE_TIMEOUT, 30
            )

        args = [
            bridge.get_jvm(),
            endpoint_description.get_interfaces(),
            proxy,
            self._executor,
            timeout,
        ]

        clazz = JavaServiceProxy

        if (
            ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE
            in endpoint_description.get_remote_configs_supported()
        ):
            clazz = ProtobufJavaServiceProxy

        return clazz(*args)

    def unimport_service(self, endpoint_description):
        # pylint: disable=W0212
        dp = self._get_distribution_provider()
        if dp:
            bridge = dp._get_bridge()
            if bridge:
                bridge.remove_import_endpoint(endpoint_description.get_id())
        ImportContainer.unimport_service(self, endpoint_description)


@ComponentFactory("py4j-distribution-provider-factory")
@Provides(
    [SERVICE_EXPORT_DISTRIBUTION_PROVIDER, SERVICE_IMPORT_DISTRIBUTION_PROVIDER]
)
@Property("_config_name", "config_name", ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Property("_namespace", "namespace", ECF_PY4J_NAMESPACE)
@Property(
    "_supported_configs",
    "supported_configs",
    [ECF_PY4J_PYTHON_HOST_CONFIG_TYPE, ECF_PY4J_PYTHON_CONSUMER_CONFIG_TYPE],
)
@Property("_supported_intents", "supported_intents",
          ECF_PY4J_SUPPORTED_INTENTS)
@Property(
    "_supported_pb_intents",
    "supported_pb_intents",
    ECF_PY4JPB_SUPPORTED_INTENTS,
)
@Property(
    "_javaport",
    prop_dot_suffix(ECF_PY4J_CONTAINER_CONFIG_TYPE, ECF_PY4J_JAVA_PORT_PROP),
    DEFAULT_PORT,
)
@Property(
    "_pythonport",
    prop_dot_suffix(ECF_PY4J_CONTAINER_CONFIG_TYPE, ECF_PY4J_PYTHON_PORT_PROP),
    DEFAULT_PYTHON_PROXY_PORT,
)
@Property(
    "_default_service_timeout",
    prop_dot_suffix(
        ECF_PY4J_CONTAINER_CONFIG_TYPE, ECF_PY4J_DEFAULT_SERVICE_TIMEOUT
    ),
    30,
)
@Instantiate("py4j-distribution-provider")
class Py4jDistributionProvider(
    DistributionProvider, Py4jServiceBridgeEventListener
):
    def __init__(self):
        super(Py4jDistributionProvider, self).__init__()
        self._bridge = None
        self._container = None
        self._queue = Queue()
        self._thread = Thread(target=self._worker)
        self._thread.daemon = True
        self._done = False
        self._lock = RLock()
        self._py4jcontainer = self._supported_pb_intents = None
        self._javaport = self._pythonport = self._default_service_timeout = None

    def _get_bridge(self):
        return self._bridge

    # Override of DistributionProvider._get_imported_configs. Returns
    # the Py4j bridge.get_id() in list
    def _get_imported_configs(self, exported_configs):
        imported_configs = []
        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in exported_configs:
            imported_configs.append(ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE)
        if ECF_PY4J_JAVA_HOST_CONFIG_TYPE in exported_configs:
            imported_configs.append(ECF_PY4J_PYTHON_HOST_CONFIG_TYPE)
        return imported_configs

    # Implementation of ImportDistributionProvider
    def supports_import(self, exported_configs, service_intents, import_props):
        # pylint: disable=W0613
        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in exported_configs:
            if self._match_intents_supported(
                service_intents, self._supported_pb_intents
            ):
                return self._container
        elif ECF_PY4J_JAVA_HOST_CONFIG_TYPE in exported_configs:
            if self._match_intents(service_intents):
                return self._container

        return None

    # Implementation of ExportDistributionProvider
    def supports_export(self, exported_configs, service_intents, export_props):
        # pylint: disable=W0613
        if self._match_intents(service_intents):
            if (
                ECF_PY4J_PYTHON_HOST_CONFIG_TYPE in exported_configs
                or ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE in exported_configs
            ):
                return self._container

        return None

    @Validate
    def _validate(self, _):
        # here is where we can get java and python ports and change the
        # defaults for connecting
        try:
            self._bridge = Py4jServiceBridge(
                service_listener=self,
                gateway_parameters=GatewayParameters(port=self._javaport),
                callback_server_parameters=CallbackServerParameters(
                    port=self._pythonport
                ),
            )
            self._bridge.connect()
        except Exception as e:
            self._bridge = None
            raise e
        # Once bridge is connected, instantiate container using bridge id
        container_props = self._prepare_container_props(
            self._supported_intents, None
        )
        if self._default_service_timeout:
            container_props[
                ECF_PY4J_DEFAULT_SERVICE_TIMEOUT
            ] = self._default_service_timeout
        self._container = self._ipopo.instantiate(
            self._config_name, self._bridge.get_id(), container_props
        )

    @Invalidate
    def _invalidate(self, _):
        if self._bridge:
            with self._lock:
                # Set done flag to True
                self._done = True
                # Trigger reading from queue in self._worker
                # with empty task
                self._queue.put((None, None, None))
            try:
                self._ipopo.invalidate(self._bridge.get_id())
            except ValueError:
                pass
            try:
                self._bridge.disconnect()
            except Exception:
                pass
            self._bridge = None
            self._container = None

    # Implementation of Py4jServiceBridgeEventListener
    def service_imported(
        self, servicebridge, endpointid, proxy, endpoint_props
    ):
        # put on task queue so no blocking, but fifo delivery to rsa
        #  _logger.info('service_imported endpointid='+endpointid)
        self._queue.put((endpointid, endpoint_props, self._handle_import))

    def service_modified(
        self, servicebridge, endpointid, proxy, endpoint_props
    ):
        # _logger.info('_service_modified endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        self._queue.put(
            (endpointid, endpoint_props, self._handle_import_update)
        )

    def service_unimported(
        self, servicebridge, endpointid, proxy, endpoint_props
    ):
        # _logger.info('_service_unimported endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        # put on task queue so no blocking, but fifo delivery to rsa
        self._queue.put(
            (endpointid,
             endpoint_props,
             self._handle_import_close))

    @PostRegistration
    def _post_reg(self, _):
        # start the thread for processing import_service import requests
        self._thread.start()

    # this is method called by self._thread.  All it does is
    # read from queue, and import/unregister imported the discovered service
    def _worker(self):
        while True:
            with self._lock:
                # If self._done flag is set, return and that's it
                if self._done:
                    return
            # otherwise block to get items from queue placed by service_imported,
            # service_modified, and service_unimported
            # called by Py4j handler thread
            item = self._queue.get()
            f = None
            try:
                # get the function from item[2]
                f = item[2]
            except Exception:
                logging.error("Exception getting code in item=%s", item)

            if f:
                try:
                    # get the endpoint description properties from item[1]
                    # and create EndpointDescription instance
                    ed = EndpointDescription(properties=item[1])
                except Exception:
                    logging.error(
                        "Exception creating endpoint description from props=%s",
                        item[1],
                    )
                else:
                    # call appropriate function
                    try:
                        f(ed)
                    except Exception:
                        logging.error("Exception invoking function=%s", f)

            # no matter what, we are done with this task
            self._queue.task_done()
