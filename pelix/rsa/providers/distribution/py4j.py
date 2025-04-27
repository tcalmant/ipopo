#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Py4j-based Distribution and Discovery Provider

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2020 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import logging
from concurrent.futures import Executor, ThreadPoolExecutor
from queue import Queue
from threading import RLock, Thread
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from osgiservicebridge.bridge import (
    JavaServiceProxy,
    Py4jServiceBridge,
    Py4jServiceBridgeEventListener,
    PythonService,
)
from osgiservicebridge.protobuf import ProtobufJavaServiceProxy, ProtobufPythonService
from py4j.java_gateway import (
    DEFAULT_PORT,
    DEFAULT_PYTHON_PROXY_PORT,
    CallbackServerParameters,
    GatewayParameters,
)

from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import ARG_BUNDLE_CONTEXT, ARG_PROPERTIES
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    PostRegistration,
    Property,
    Provides,
    Validate,
    ValidateComponent,
)
from pelix.rsa import prop_dot_suffix
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.distribution import (
    Container,
    ExportContainer,
    ExportDistributionProvider,
    ImportContainer,
    ImportDistributionProvider,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
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


# ------------------------------------------------------------------------------
@ComponentFactory(ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Provides([ExportContainer, ImportContainer])
class Py4jContainer(ExportContainer, ImportContainer):

    def __init__(self, max_workers: int=5) -> None:
        ExportContainer.__init__(self)
        ImportContainer.__init__(self)
        self._max_workers = max_workers
        self._executor: Optional[Executor] = None

    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context: BundleContext, container_props: Dict[str, Any]) -> None:
        Container._validate_component(self, bundle_context, container_props)
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    @Invalidate
    def _invalidate_component(self, context: BundleContext) -> None:
        Container._invalidate_component(self, context)
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None

    def get_connected_id(self) -> Optional[str]:
        return ExportContainer.get_connected_id(self)

    def _export_service(self, svc: Any, ed: EndpointDescription) -> None:
        # modify svc class to have appropriate metadata for py4j
        timeout = ed.get_osgi_basic_timeout()
        if not timeout:
            timeout = 30

        dp = cast(Py4jDistributionProvider, self._get_distribution_provider())

        args = [
            dp._get_bridge(),
            ed.get_interfaces(),
            svc,
            self._executor,
            timeout,
        ]

        if ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE in ed.get_remote_configs_supported():
            clazz = ProtobufPythonService
        else:
            clazz = PythonService

        psvc = clazz(*args)

        dp._get_bridge().export(psvc, ed.get_properties())
        ExportContainer._export_service(self, psvc, ed)

    def _unexport_service(self, ed: EndpointDescription) -> None:
        dp = cast(Py4jDistributionProvider, self._get_distribution_provider())
        if dp:
            bridge = dp._get_bridge()
            if bridge:
                bridge.unexport(ed.get_id())
        ExportContainer._unexport_service(self, ed)

    def _prepare_proxy(self, endpoint_description: EndpointDescription) -> Any:
        # pylint: disable=W0212
        # lookup the bridge proxy associated with the
        # endpoint_description.get_id()
        dp = cast(Py4jDistributionProvider, self._get_distribution_provider())
        bridge = dp._get_bridge()
        proxy = bridge.get_import_endpoint(endpoint_description.get_id())[0]
        timeout = endpoint_description.get_osgi_basic_timeout()
        if not timeout:
            timeout = self._container_props.get(ECF_PY4J_DEFAULT_SERVICE_TIMEOUT, 30)

        args = [
            bridge.get_jvm(),
            endpoint_description.get_interfaces(),
            proxy,
            self._executor,
            timeout,
        ]

        clazz = JavaServiceProxy

        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in endpoint_description.get_remote_configs_supported():
            clazz = ProtobufJavaServiceProxy

        return clazz(*args)

    def unimport_service(self, endpoint_description: EndpointDescription) -> None:
        dp = cast(Py4jDistributionProvider, self._get_distribution_provider())
        if dp is not None:
            bridge = dp._get_bridge()
            if bridge:
                bridge.remove_import_endpoint(endpoint_description.get_id())
        ImportContainer.unimport_service(self, endpoint_description)


# Distribution Provider property names
ECF_PY4J_JAVA_PORT_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "javaport"])
ECF_PY4J_JAVA_PORT_DEFAULT = DEFAULT_PORT
ECF_PY4J_PYTHON_PORT_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "pythonport"])
ECF_PY4J_PYTHON_PORT_DEFAULT = DEFAULT_PYTHON_PROXY_PORT
ECF_PY4J_SERVICE_TIMEOUT_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "defaultservicetimeout"])
ECF_PY4J_SERVICE_TIMEOUT_DEFAULT = 30
ECF_PY4J_USE_IMPORT_HOOK_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "useimporthook"])
ECF_PY4J_USE_IMPORT_HOOK_DEFAULT = False
ECF_PY4J_GATEWAY_PARAMS_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "gatewayparams"])
ECF_PY4J_GATEWAY_PARAMS_DEFAULT = None
ECF_PY4J_CALLBACKSERVER_PARAMS_PROP = ".".join([ECF_PY4J_CONTAINER_CONFIG_TYPE, "callbackserverparams"])
ECF_PY4J_CALLBACKSERVER_PARAMS_DEFAULT = None


@ComponentFactory("py4j-distribution-provider-factory")
@Provides([ExportDistributionProvider, ImportDistributionProvider])
@Property("_config_name", "config_name", ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Property("_namespace", "namespace", ECF_PY4J_NAMESPACE)
@Property(
    "_supported_configs",
    "supported_configs",
    [ECF_PY4J_PYTHON_HOST_CONFIG_TYPE, ECF_PY4J_PYTHON_CONSUMER_CONFIG_TYPE],
)
@Property("_supported_intents", "supported_intents", ECF_PY4J_SUPPORTED_INTENTS)
@Property(
    "_supported_pb_intents",
    "supported_pb_intents",
    ECF_PY4JPB_SUPPORTED_INTENTS,
)
@Property(
    "_java_port",
    ECF_PY4J_JAVA_PORT_PROP,
    ECF_PY4J_JAVA_PORT_DEFAULT,
)
@Property(
    "_python_port",
    ECF_PY4J_PYTHON_PORT_PROP,
    ECF_PY4J_PYTHON_PORT_DEFAULT,
)
@Property(
    "_default_service_timeout",
    ECF_PY4J_SERVICE_TIMEOUT_PROP,
    ECF_PY4J_SERVICE_TIMEOUT_DEFAULT,
)
@Property(
    "_import_hook",
    ECF_PY4J_USE_IMPORT_HOOK_PROP,
    ECF_PY4J_USE_IMPORT_HOOK_DEFAULT
)
@Property(
    "_gateway_params",
    ECF_PY4J_GATEWAY_PARAMS_PROP,
    ECF_PY4J_GATEWAY_PARAMS_DEFAULT
)
@Property(
    "_callback_server_params",
    ECF_PY4J_CALLBACKSERVER_PARAMS_PROP,
    ECF_PY4J_CALLBACKSERVER_PARAMS_DEFAULT
)
@Instantiate("py4j-distribution-provider")
class Py4jDistributionProvider(
    ExportDistributionProvider, ImportDistributionProvider, Py4jServiceBridgeEventListener
):
    _java_port: Optional[int]
    _python_port: Optional[int]
    _default_service_timeout: Optional[float]
    _import_hook: bool
    _gateway_params: Optional[GatewayParameters]
    _callback_server_params: Optional[CallbackServerParameters]

    def __init__(self) -> None:
        ExportDistributionProvider.__init__(self)
        ImportDistributionProvider.__init__(self)
        Py4jServiceBridgeEventListener.__init__(self)

        self._bridge: Optional[Py4jServiceBridge] = None
        self._container: Optional[Container] = None
        self._queue: Queue[
            Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Callable[[EndpointDescription], Any]]]
        ] = Queue()
        self._thread = Thread(target=self._worker, daemon=True)
        self._done = False
        self._lock = RLock()
        self._supported_pb_intents = None

    def _get_bridge(self) -> Py4jServiceBridge:
        if self._bridge is None:
            raise ValueError("Bridge is not available")

        return self._bridge

    # Override of DistributionProvider._get_imported_configs. Returns
    # the Py4j bridge.get_id() in list
    def _get_imported_configs(self, exported_configs: List[str]) -> List[str]:
        imported_configs: List[str] = []

        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in exported_configs:
            imported_configs.append(ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE)

        if ECF_PY4J_JAVA_HOST_CONFIG_TYPE in exported_configs:
            imported_configs.append(ECF_PY4J_PYTHON_HOST_CONFIG_TYPE)

        return imported_configs

    # Implementation of ImportDistributionProvider
    def supports_import(
        self,
        exported_configs: Optional[List[str]],
        service_intents: Optional[List[str]],
        import_props: Dict[str, Any],
    ) -> Optional[ImportContainer]:
        if exported_configs:
            if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in exported_configs:
                if self._match_intents_supported(service_intents, self._supported_pb_intents):
                    return cast(ImportContainer, self._container)
            elif ECF_PY4J_JAVA_HOST_CONFIG_TYPE in exported_configs:
                if self._match_intents(service_intents):
                    return cast(ImportContainer, self._container)

        return None

    # Implementation of ExportDistributionProvider
    def supports_export(
        self,
        exported_configs: Optional[List[str]],
        service_intents: Optional[List[str]],
        export_props: Dict[str, Any],
    ) -> Optional[ExportContainer]:
        if exported_configs and self._match_intents(service_intents):
            if (
                ECF_PY4J_PYTHON_HOST_CONFIG_TYPE in exported_configs
                or ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE in exported_configs
            ):
                return cast(ExportContainer, self._container)

        return None

    @Validate
    def _validate(self, _: BundleContext) -> None:
        # here is where we can get java and python ports and change the
        # defaults for connecting
        try:
            self._bridge = Py4jServiceBridge(
                service_listener=self,
                gateway_parameters=GatewayParameters(
                    port=self._java_port or DEFAULT_PORT
                    ) if not self._gateway_params else self._gateway_params,
                callback_server_parameters=CallbackServerParameters(
                    port=self._python_port or DEFAULT_PYTHON_PROXY_PORT
                ) if not self._callback_server_params else self._callback_server_params,
            )
            from osgiservicebridge.bridge import OSGIPythonModulePathHook
            self._bridge.connect(path_hook=OSGIPythonModulePathHook(self._bridge) if self._import_hook else None)
        except Exception as e:
            self._bridge = None
            raise e
        # Once bridge is connected, instantiate container using bridge id
        container_props = self._prepare_container_props(self._supported_intents, {})
        if self._default_service_timeout:
            container_props[ECF_PY4J_SERVICE_TIMEOUT_DEFAULT] = self._default_service_timeout
        self._container = self._ipopo.instantiate(self._config_name, self._bridge.get_id(), container_props)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        if self._bridge is not None:
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
        self, servicebridge: Py4jServiceBridge, endpointid: str, proxy: Any, endpoint_props: Dict[str, Any]
    ) -> None:
        # put on task queue so no blocking, but fifo delivery to rsa
        #  _logger.info('service_imported endpointid='+endpointid)
        self._queue.put((endpointid, endpoint_props, self._handle_import))

    def service_modified(
        self, servicebridge: Py4jServiceBridge, endpointid: str, proxy: Any, endpoint_props: Dict[str, Any]
    ) -> None:
        # _logger.info('_service_modified endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        self._queue.put((endpointid, endpoint_props, self._handle_import_update))

    def service_unimported(
        self, servicebridge: Py4jServiceBridge, endpointid: str, proxy: Any, endpoint_props: Dict[str, Any]
    ) -> None:
        # _logger.info('_service_unimported endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        # put on task queue so no blocking, but fifo delivery to rsa
        self._queue.put((endpointid, endpoint_props, self._handle_import_close))

    @PostRegistration
    def _post_reg(self, _: ServiceReference[Any]) -> None:
        # start the thread for processing import_service import requests
        self._thread.start()

    # this is method called by self._thread.  All it does is
    # read from queue, and import/unregister imported the discovered service
    def _worker(self) -> None:
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
                _logger.error("Exception getting code in item=%s", item)

            if f is not None:
                try:
                    # get the endpoint description properties from item[1]
                    # and create EndpointDescription instance
                    ed = EndpointDescription(properties=item[1])
                except Exception:
                    _logger.error(
                        "Exception creating endpoint description from props=%s",
                        item[1],
                    )
                else:
                    # call appropriate function
                    try:
                        f(ed)
                    except Exception:
                        _logger.error("Exception invoking function=%s", f)

            # no matter what, we are done with this task
            self._queue.task_done()
