import logging
from _thread import RLock
from threading import Thread
from typing import Annotated, Any, Callable, List

from mcp.server.auth.provider import OAuthAuthorizationServerProvider
from mcp.server.fastmcp.exceptions import InvalidSignature
from mcp.server.fastmcp.prompts import PromptManager
from mcp.server.fastmcp.resources import ResourceManager
from mcp.server.fastmcp.server import FastMCP, Settings, lifespan_wrapper
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.tools.tool_manager import ToolManager
from mcp.server.fastmcp.utilities.func_metadata import (
    ArgModelBase,
    FuncMetadata,
    _get_typed_annotation,
)
from mcp.server.fastmcp.utilities.logging import configure_logging
from mcp.server.lowlevel.server import Server as MCPServer
from mcp.server.lowlevel.server import lifespan as default_lifespan
from mcp.server.streamable_http import EventStore
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import ToolAnnotations
from pydantic import Field, WithJsonSchema, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from starlette.routing import Route

from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    Bind,
    ComponentFactory,
    Instantiate,
    Property,
    Requires,
    Unbind,
    Validate,
)
from samples.remotetoolsserver.descriptions import get_tool_descriptions_from_service

from .descriptions import ToolDescription, ToolParamDescription

logger = logging.getLogger(__name__)


# Subclass of mcp.server.fastmcp.tools.tool_manager.ToolManager
# This is necessary so that the ToolManager used by the RemoteToolsFastMCP
# class and have new methods:  add_tool_from_description
class RemoteToolManager(ToolManager):
    _lock: RLock = RLock()

    def get_tool(self, name: str) -> Tool | None:
        with self._lock:
            return ToolManager.get_tool(self, name)

    def _params_metadata(self, param_descs: list[ToolParamDescription]) -> FuncMetadata:
        dynamic_pydantic_model_params: dict[str, Any] = {}

        for param_desc in param_descs:
            if param_desc.name.startswith("_"):
                raise InvalidSignature(f"Parameter {param_desc.name} cannot start with '_'")
            annotation = Annotated[
                Any,
                Field(description=param_desc.description),
                WithJsonSchema({"title": param_desc.name, "type": "string"}),
            ]
            field_info = FieldInfo.from_annotated_attribute(
                _get_typed_annotation(annotation, {}),
                PydanticUndefined,
            )
            dynamic_pydantic_model_params[param_desc.name] = (
                field_info.annotation,
                field_info,
            )
        arguments_model = create_model(
            f"{param_desc.name}Arguments",
            **dynamic_pydantic_model_params,
            __base__=ArgModelBase,
        )
        return FuncMetadata(arg_model=arguments_model)

    def _from_tool_description(self, service_proxy, tool_description: ToolDescription) -> Tool:
        func_name = tool_description.name
        annotations = tool_description.tool_annotations

        args_metadata = self._params_metadata(tool_description.tool_param_descriptions)
        parameters = args_metadata.arg_model.model_json_schema()

        def _call_tool(**kwargs):
            args = kwargs.values()
            return getattr(service_proxy, func_name)(*args)

        return Tool(
            fn=_call_tool,
            name=func_name,
            description=tool_description.description,
            parameters=parameters,
            fn_metadata=args_metadata,
            is_async=False,
            context_kwarg=None,
            annotations=annotations,
        )

    def add_tool_from_description(self, service_proxy, tool_description: ToolDescription) -> Tool:
        tool = self._from_tool_description(service_proxy, tool_description)
        with self._lock:
            existing = self._tools.get(tool.name)
            if existing:
                if self.warn_on_duplicate_tools:
                    logger.warning(f"Tool already exists: {tool.name}")
                return existing
            self._tools[tool.name] = tool
        return tool

    def add_tool(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
    ) -> Tool:
        # this method overrides superclass as guards the super class
        # add_tool with the _lock
        with self._lock:
            return ToolManager.add_tool(self, fn, name=name, description=description, annotations=annotations)

    def list_tools(self) -> list[Tool]:
        # this method overrides superclass as guards the super class
        # list_tools with the _lock
        logger.debug("list_tools=")
        with self._lock:
            return ToolManager.list_tools(self)

    def remove_tool(self, name: str):
        with self._lock:
            return self._tools.pop(name, None)


# Subclass of FastMCP server.  Subclassing allows adding of add_tools_from_service
# and remove_tools_from_service, which are methods that dynamically adds and remove
# remote tools, implemented in Java as OSGi remote services
class RemoteToolFastMCP(FastMCP):
    _tool_descriptions: dict = {}

    def __init__(
        self,
        name: str | None = None,
        instructions: str | None = None,
        auth_server_provider: OAuthAuthorizationServerProvider[Any, Any, Any] | None = None,
        event_store: EventStore | None = None,
        *,
        tools: list[Tool] | None = None,
        **settings: Any,
    ):
        self.settings = Settings(**settings)

        self._mcp_server = MCPServer(
            name=name or "FastMCP",
            instructions=instructions,
            lifespan=(
                lifespan_wrapper(self, self.settings.lifespan) if self.settings.lifespan else default_lifespan
            ),
        )
        self._tool_manager = RemoteToolManager(
            tools=tools, warn_on_duplicate_tools=self.settings.warn_on_duplicate_tools
        )
        self._resource_manager = ResourceManager(
            warn_on_duplicate_resources=self.settings.warn_on_duplicate_resources
        )
        self._prompt_manager = PromptManager(
            warn_on_duplicate_prompts=self.settings.warn_on_duplicate_prompts
        )
        if (self.settings.auth is not None) != (auth_server_provider is not None):
            raise ValueError(
                "settings.auth must be specified if and only if auth_server_provider is specified"
            )
        self._auth_server_provider = auth_server_provider
        self._event_store = event_store
        self._custom_starlette_routes: list[Route] = []
        self.dependencies = self.settings.dependencies
        self._session_manager: StreamableHTTPSessionManager | None = None

        # Set up MCP protocol handlers
        self._setup_handlers()

        # Configure logging
        configure_logging(self.settings.log_level)

    def add_tools_from_service(self, service_proxy: Any, service_interface: str) -> None:
        ptool_descriptions = get_tool_descriptions_from_service(service_proxy, service_interface)
        with self._tool_manager._lock:
            for desc in ptool_descriptions:
                tool = self._tool_manager.add_tool_from_description(service_proxy, desc)
                if tool:
                    self._tool_descriptions[desc.name] = (
                        service_proxy,
                        service_interface,
                        desc,
                    )

    def remove_tools_from_service(self, service_proxy: Any, service_interface: str):
        with self._tool_manager._lock:
            descs = [*self._tool_descriptions.values()]
            for val in descs:
                if val[0] == service_proxy and val[1] == service_interface:
                    self._tool_descriptions.pop(val[2].name)
                    self._tool_manager.remove_tool(val[2].name)


# Declaration of the service interface classname.  When an iPopo component is annotatied
# with the @Requires annotation as the RemoteToolsFastMCPServer is below, this means that
# when a service instance implementing that interface is registered in the pelix service
# registry that it will be added to the _tools_services by calling the method annotated
# with @Bind below.  When the service is unregistered the method annotated with the @Unbind
# annotation will be called.  This corresponds to the fully qualified name of the java
# interface located here:
# https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.ai.mcp.toolservice.api/src/org/eclipse/ecf/examples/ai/mcp/toolservice/api/ArithmeticTools.java
ARITHMETIC_TOOL_SERVICE_INTERFACE = "org.eclipse.ecf.examples.ai.mcp.toolservice.api.ArithmeticTools"


# Component that is created and started by framework.  Once validated
# see _validate method, an instance of RemoteToolFastMCP (above)
# is created and run in new thread.  When instances of ARITHMETIC_TOOLS_SERVICE_INTERFACE
# are imported via RSA, the _bind_tool_service method is called and
# any tool descriptions found are added to set of tools available to the
# RemoteToolManager class declared above
@ComponentFactory("remote-tools-fastmcp-server-factory")
@Instantiate("remote-tools-fastmcp-server")
@Requires(
    "_tools_services",
    ARITHMETIC_TOOL_SERVICE_INTERFACE,
    True,
    True,
    None,
    False,
)
@Property("_name", "remotetoolsfastmpcserver.name", "RemoteToolsFastMCPServer")
@Property("_instructions", "remotetoolsfastmpcserver.instructions", "RemoteToolsFastMCPServer")
class RemoteToolsFastMCPServer:
    _tools_services: List[Any]
    _name: str | None = None
    _instructions: str | None = None

    def __init__(self):
        self._mcp = None

    @Validate
    def _validate(self, bcontext: BundleContext) -> None:
        # create a RemoteToolFastMCP instance
        self._mcp = RemoteToolFastMCP(name=self._name, instructions=self._instructions)
        # Run separate thread so that the mcp server anyio doesn't use same thread
        # calling this method (a pelix thread)
        t = Thread(target=self._mcp.run, name="RemoteTools Thread")
        t.daemon = True
        t.start()

    @Bind
    def _bind_tool_service(self, service_proxy: Any, service_reference: ServiceReference):
        self._mcp.add_tools_from_service(service_proxy, ARITHMETIC_TOOL_SERVICE_INTERFACE)

    @Unbind
    def _unbind_tool_service(self, service_proxy: Any, service_reference: ServiceReference):
        self._mcp.remove_tools_from_service(service_proxy, ARITHMETIC_TOOL_SERVICE_INTERFACE)
