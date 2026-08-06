from dataclasses import dataclass
from typing import Any

from mcp.types import ToolAnnotations


# Dataclasses to represent ToolDescription, ToolParamDescription, ToolResultDescription
@dataclass
class ToolParamDescription:
    name: str = ""
    description: str = ""
    required: bool = True


@dataclass
class ToolResultDescription:
    description: str = ""


@dataclass
class ToolDescription:
    name: str = ""
    description: str = ""
    tool_param_descriptions: list[ToolParamDescription] = None
    result_description: ToolResultDescription = None
    tool_annotations: list[ToolAnnotations] = None


# convert a single Java ToolDescription object to a puthon ToolDescription
def convert_tool_description(tool_desc: Any) -> ToolDescription:
    tool_param_descs = [
        ToolParamDescription(d.name(), d.description(), d.required())
        for d in tool_desc.toolParamDescriptions()
    ]
    tool_result_desc = ToolResultDescription(tool_desc.resultDescription().description())
    d = tool_desc.toolAnnotationsDescription()
    tool_annotations = (
        ToolAnnotations(
            destructiveHint=d.destructiveHint(),
            idempotentHint=d.idempotentHint(),
            openWorldHint=d.openWorldHint(),
            readOnlyHint=d.readOnlyHint(),
            title=d.title(),
        )
        if d
        else None
    )
    return ToolDescription(
        tool_desc.name(),
        tool_desc.description(),
        tool_param_descs,
        tool_result_desc,
        tool_annotations,
    )


# convert a list of Java ToolDescription object to a puthon ToolDescription
def convert_tool_descriptions(tool_descs: list[Any]) -> list[ToolDescription]:
    return [convert_tool_description(tool_desc) for tool_desc in tool_descs]


# Given a Java service instance and a service interface implemented by that service
# get and then convert all tool descriptions by calling service.getToolDescriptions
# which assumes that the service implements (or extends) the org.eclipse.ecf.ai.mcp.service.ToolGroupService
# interface class
def get_tool_descriptions_from_service(service: Any, service_interface: str):
    java_descs = service.getToolDescriptions(service_interface)
    return convert_tool_descriptions(java_descs)
