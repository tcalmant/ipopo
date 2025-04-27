#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

XmlRpc-on-HttpService-based Export and Import Distribution Providers

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

import xmlrpc.client as xmlrpclib
from concurrent.futures import Executor
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from xmlrpc.server import SimpleXMLRPCDispatcher

from pelix.framework import BundleContext
from pelix.http import AbstractHTTPServletRequest, AbstractHTTPServletResponse, HTTPService, Servlet
from pelix.ipopo.constants import ARG_BUNDLE_CONTEXT, ARG_PROPERTIES
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    ValidateComponent,
)
from pelix.rsa import prop_dot_suffix
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.distribution import (
    SERVICE_EXPORT_CONTAINER,
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER,
    SERVICE_IMPORT_CONTAINER,
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER,
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

# ------------------------------------------------------------------------------
# XmlRpc Distribution Provider Constants. Note that to get interoperability with
# Java-based ECF RSA providers, these must match the Java-side constants.
ECF_XMLRPC_SERVER_CONFIG = "ecf.xmlrpc.server"
ECF_XMLRPC_CLIENT_CONFIG = "ecf.xmlrpc.client"
ECF_XMLRPC_SUPPORTED_CONFIGS = [ECF_XMLRPC_SERVER_CONFIG]
ECF_XMLRPC_NAMESPACE = "ecf.namespace.xmlrpc"
ECF_XMLRPC_SUPPORTED_INTENTS = ["osgi.basic", "osgi.async"]
ECF_XMLRPC_PATH_PROP = "path"
ECF_XMLRPC_TIMEOUT_PROP = "timeout"
ECF_XMLRPC_HOSTNAME_PROP = "hostname"

# ------------------------------------------------------------------------------


class ServerDispatcher(SimpleXMLRPCDispatcher, Servlet):
    """
    ServerDispatcher (subclass of SimpleXMLRPCDispatcher)
    uses ECF remote service id to identify the service
    for method invocation requests.  See do_POST and _dispatch
    for the actual method invocation.
    """

    def __init__(
        self,
        dispatch_func: Callable[..., Any],
        timeout: Optional[float] = None,
        executor: Optional[Executor] = None,
    ) -> None:
        super(ServerDispatcher, self).__init__(allow_none=True)
        self._dispatch_func = dispatch_func
        self._timeout = timeout
        self._executor = executor

    def do_POST(self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse) -> None:
        # pylint: disable=C0103
        data = request.read_data().decode()
        result = self._marshaled_dispatch(data, self._dispatch)
        response.send_content(200, result, "text/xml")

    def _dispatch(self, method: Optional[str], params: Any) -> Any:
        if method is None:
            raise Exception("No method to dispatch given")
        obj_method_list = method.split(".")
        if not len(obj_method_list) == 2:
            raise Exception(
                "_dispatch: invalid method=" + method + ".  Must be of form <objectid>.<methodname>"
            )
        # and call _dispatch_func/3
        if self._executor:
            return self._executor.submit(
                self._dispatch_func,
                obj_method_list[0],
                obj_method_list[1],
                params,
            ).result(self._timeout)

        return self._dispatch_func(obj_method_list[0], obj_method_list[1], params)


# ------------------------------------------------------------------------------
# Implementation of SERVICE_EXPORT_CONTAINER
@ComponentFactory(ECF_XMLRPC_SERVER_CONFIG)
@Provides(SERVICE_EXPORT_CONTAINER)
class XmlRpcExportContainer(ExportContainer):
    """
    Subclass of ExportContainer created by the XmlRpcExportDistributionProvider
    at export time. The @ComponentFactory annotation on this class uses the
    ECF_XMLRPC_SERVER_CONFIG = 'ecf.xmlrpc.server' as it's factory identifier.
    This factory name be the same as the @Property('_config_name',
    'config_name', ECF_XMLRPC_SERVER_CONFIG) in the
    XmlRpcExportDistributionProvider below
    """

    def _get_distribution_provider(self) -> "XmlRpcExportDistributionProvider":
        return cast(XmlRpcExportDistributionProvider, super()._get_distribution_provider())

    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context: BundleContext, container_props: Dict[str, Any]) -> None:
        # pylint: disable=W0212
        ExportContainer._validate_component(self, bundle_context, container_props)
        timeout = container_props.get(ECF_XMLRPC_TIMEOUT_PROP, None)
        dp = self._get_distribution_provider()
        executor = ThreadPoolExecutor(max_workers=5)
        # register the ServerDispatcher instance our uri_path
        dp._httpservice.register_servlet(
            dp._uri_path,
            ServerDispatcher(self._dispatch_exported, timeout, executor),
        )

    @Invalidate
    def _invalidate_component(self, bundle_context: BundleContext) -> None:
        # pylint: disable=W0212
        """
        First invalidate by unregistering the servlet/dispatcher,
        and then call super._invalidate
        """
        try:
            dp = self._get_distribution_provider()
            dp._httpservice.unregister(dp._uri_path)
            ExportContainer._invalidate_component(self, bundle_context)
        except:
            pass


# ------------------------------------------------------------------------------
# Implementation of SERVICE_EXPORT_DISTRIBUTION_PROVIDER
@ComponentFactory("xmlrpc-export-distribution-provider-factory")
@Provides(SERVICE_EXPORT_DISTRIBUTION_PROVIDER)
@Property("_config_name", "config_name", ECF_XMLRPC_SERVER_CONFIG)
@Property("_namespace", "namespace", ECF_XMLRPC_NAMESPACE)
@Property("_supported_configs", "supported_configs", ECF_XMLRPC_SUPPORTED_CONFIGS)
@Property("_supported_intents", "supported_intents", ECF_XMLRPC_SUPPORTED_INTENTS)
@Requires("_httpservice", HTTPService)
@Property(
    "_uri_path",
    prop_dot_suffix(ECF_XMLRPC_SERVER_CONFIG, ECF_XMLRPC_PATH_PROP),
    "/xml-rpc",
)
@Property(
    "_timeout",
    prop_dot_suffix(ECF_XMLRPC_SERVER_CONFIG, ECF_XMLRPC_TIMEOUT_PROP),
    30,
)
@Property(
    "_hostname",
    prop_dot_suffix(ECF_XMLRPC_SERVER_CONFIG, ECF_XMLRPC_HOSTNAME_PROP),
    "localhost",
)
@Instantiate("xmlrpc-export-distribution-provider")
class XmlRpcExportDistributionProvider(ExportDistributionProvider):
    """
    ExportDistributionProvider subclass.  The _config_name property
    must be set to the same value as the ExportContainer class factory,
    as it is with the XmlRpcExportContainer class above (ECF_XMLRPC_SERVER_CONFIG).
    This is necessary so that at export time, this provider will used
    the factory with name ECF_XMLRPC_SERVER_CONFIG to create ExportContainer
    instances as needed.

    Note that this distribution provider uses the injected _httpservice
    to register servlets via the ExportContainer._validate_component call
    as implemented in XmlRpcExportContainer._validate_component.
    """

    _httpservice: HTTPService

    def __init__(self) -> None:
        super(XmlRpcExportDistributionProvider, self).__init__()
        self._uri_path: str = ""
        self._timeout: Optional[float] = None
        self._hostname: Optional[str] = None

    def _prepare_container_props(
        self, service_intents: Optional[List[str]], export_props: Dict[str, Any]
    ) -> Dict[str, Any]:
        container_props = ExportDistributionProvider._prepare_container_props(
            self, service_intents, export_props
        )
        if self._timeout:
            container_props[ECF_XMLRPC_TIMEOUT_PROP] = self._timeout
        return container_props

    def _prepare_container_id(self, container_props: Dict[str, Any]) -> str:
        """
        This method is called prior to actual container creation in order to
        create the name/id of the ExportContainer to be subsequently created
        via ipopo.instantiate(ECF_XMLRPC_SERVER_CONFIG,container_id,props).

        The String returned from this method is used in the instantiate call as
        the container_id.
        """
        protocol = "https" if self._httpservice.is_https() else "http"
        hostname = cast(Optional[str], container_props.get(ECF_XMLRPC_HOSTNAME_PROP, None))
        if not hostname:
            hostname = self._hostname
            if not hostname:
                hostname = self._httpservice.get_hostname()

        port = cast(Optional[int], container_props.get("port"))
        if not port:
            port = self._httpservice.get_access()[1]

        uri = f"{protocol}://{hostname}:{port}"
        return uri + self._uri_path


# ------------------------------------------------------------------------------
# Implementation of SERVICE_IMPORT_CONTAINER


@ComponentFactory(ECF_XMLRPC_CLIENT_CONFIG)
@Provides(SERVICE_IMPORT_CONTAINER)
class XmlRpcImportContainer(ImportContainer):
    """
    ImportContainer created via the XmlRpcImportDistributionProvider
    as needed at runtime.  The @ComponentFactory(ECF_XMLRPC_CLIENT_CONFIG) is
    used at to create an instance of this container at import-time.
    """

    def _prepare_proxy(self, endpoint_description: EndpointDescription) -> Any:
        """
        This method is called as part of RSA.import_service.  In this case
        an instance of XmlRpcProxy declared below is returned as the object
        representing the imported remote service (proxy).  Once returned,
        this proxy is registered with locals service registry.
        When a consumer retrieves this service and calls a method, the
        __getattr__ method (below) is and this make the remote call
        with a string: <objectid>.<method> using the
        xmlrpc.client.ServerProxy
        """

        class XmlRpcProxy:
            def __init__(self, get_remoteservice_id: Tuple[Tuple[Any, str], int]) -> None:
                self._url = get_remoteservice_id[0][1]
                self._rsid = str(get_remoteservice_id[1])

            def __getattr__(self, name: str) -> Any:
                return getattr(
                    xmlrpclib.ServerProxy(self._url, allow_none=True),
                    f"{self._rsid}.{name}",
                )

        # create instance of XmlRpcProxy and pass in remoteservice id:
        # ((ns,cid),get_remoteservice_id)
        return XmlRpcProxy(endpoint_description.get_remoteservice_id())


# ------------------------------------------------------------------------------
# Implementation of SERVICE_IMPORT_DISTRIBUTION_PROVIDER
@ComponentFactory("xmlrpc-import-distribution-provider-factory")
@Provides(SERVICE_IMPORT_DISTRIBUTION_PROVIDER)
@Property("_config_name", "config_name", ECF_XMLRPC_CLIENT_CONFIG)
@Property("_namespace", "namespace", ECF_XMLRPC_NAMESPACE)
@Property("_supported_configs", "supported_configs", ECF_XMLRPC_SUPPORTED_CONFIGS)
@Property("_supported_intents", "supported_intents", ECF_XMLRPC_SUPPORTED_INTENTS)
@Instantiate("xmlrpc-import-distribution-provider")
class XmlRpcImportDistributionProvider(ImportDistributionProvider):
    """
    We get all necessary methods from ImportDistributionProvider
    """

    ...
