"""Manual of an MCP server's tools, resources and prompts for the LLM.

Pure transformation: JSON Schemas and server metadata in, text out. It does
not talk to any server, so it can be tested with plain dictionaries.
"""

from typing import Any

from mcp.types import Tool

_JSON_TYPES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "null": "None",
    "array": "list",
    "object": "dict",
}


def _schema_type(schema: dict[str, Any]) -> str:
    """Python-style type name for a JSON Schema (list[str], int | None...)."""
    variants = schema.get("anyOf") or schema.get("oneOf")
    if variants:
        return " | ".join(_schema_type(variant) for variant in variants)
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(_schema_type({"type": item}) for item in kind)
    if kind == "array" and "items" in schema:
        return f"list[{_schema_type(schema['items'])}]"
    values = schema.get("additionalProperties")
    if kind == "object" and isinstance(values, dict):
        return f"dict[str, {_schema_type(values)}]"
    return _JSON_TYPES.get(str(kind), "Any")


def _return_type(tool: Tool) -> str:
    """Type of the value a tool function returns (see _result_value)."""
    schema = tool.output_schema
    if not schema:
        return "str"
    properties = schema.get("properties", {})
    if set(properties) == {"result"}:
        return _schema_type(properties["result"])
    return _schema_type(schema)


def _signature(tool: Tool) -> str:
    """Python-like signature: name(a: int, b: str = 'x') -> str."""
    schema = tool.input_schema
    required = set(schema.get("required", []))
    params = []
    for name, prop in schema.get("properties", {}).items():
        param = f"{name}: {_schema_type(prop)}"
        if name not in required:
            param += f" = {prop.get('default')!r}"
        params.append(param)
    return f"{tool.name}({', '.join(params)}) -> {_return_type(tool)}"


def _summary(description: str | None) -> str:
    """First line of a description, or an empty string."""
    lines = (description or "").strip().splitlines()
    return lines[0] if lines else ""


def _entry(head: str, description: str | None) -> str:
    """One manual line: '- head: summary' (summary only if any)."""
    summary = _summary(description)
    return f"- {head}: {summary}" if summary else f"- {head}"


def build_manual(
    tools: list[Tool],
    resources: list[dict[str, str]],
    prompts: list[dict[str, Any]],
) -> str:
    """Manual text: one line per tool, plus resources and prompts if any."""
    lines = ["Tools (call them as Python functions):"]
    lines += [_entry(_signature(tool), tool.description) for tool in tools]
    if resources:
        lines += ["", "Resources (read_resource(uri) -> str):"]
        lines += [_entry(r["uri"], r["description"]) for r in resources]
    if prompts:
        lines += ["", "Prompts (get_prompt(name, **arguments) -> str):"]
        lines += [
            _entry(
                f"{p['name']}({', '.join(p['arguments'])})", p["description"]
            )
            for p in prompts
        ]
    return "\n".join(lines)
