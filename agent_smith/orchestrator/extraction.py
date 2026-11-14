# agent_smith/orchestrator/extraction.py
# A universal method for extracting code blocks from LLM response
import json
import re


def extract_code(llm_output: str) -> str:
    """A universal method for extracting code blocks from LLM response."""
    python_pattern = r"```(?:python)?\s*(.*?)\s*```"
    match = re.search(python_pattern, llm_output, re.DOTALL)
    if match:
        return match.group(1).strip()

    tool_call_pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
    tc_match = re.search(tool_call_pattern, llm_output, re.DOTALL)
    if tc_match:
        try:
            data = json.loads(tc_match.group(1))
            name = data.get("name")
            args = data.get("arguments", {})
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
            return f"result = {name}({args_str})\nprint(result)"
        except Exception:
            pass

    invoke_pattern = r'<invoke\s+name=["\'](.*?)["\']>(.*?)</invoke>'
    inv_match = re.search(invoke_pattern, llm_output, re.DOTALL)
    if inv_match:
        func_name = inv_match.group(1)
        params_content = inv_match.group(2)
        param_matches = re.findall(
            r'<parameter\s+name=["\'](.*?)["\']>(.*?)</parameter>',
            params_content,
            re.DOTALL,
        )
        if param_matches:
            args_str = ", ".join(
                f'{p[0]}="{p[1].strip()}"' for p in param_matches
            )
            return f"result = {func_name}({args_str})\nprint(result)"

    react_pattern = (
        r"Action:\s*([a-zA-Z0-9_]+)\s*"
        r"(?:\\n|\n)\s*"
        r"Action\s*Input:\s*"
        r"(.+?)(?:\n|$)"
    )
    react_match = re.search(
        react_pattern,
        llm_output,
        re.IGNORECASE | re.DOTALL
    )
    if react_match:
        func_name = react_match.group(1).strip()
        raw_input = react_match.group(2).strip()

        try:
            if raw_input.startswith("{") and raw_input.endswith("}"):
                args_dict = json.loads(raw_input)
                args_str = ", ".join(
                    f"{k}={v!r}" for k, v in args_dict.items()
                )
                return f"result = {func_name}({args_str})\nprint(result)"
            else:
                return f"result = {func_name}({raw_input})\nprint(result)"
        except Exception:
            pass

    return llm_output.strip()
