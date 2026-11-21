# Specific Logic and Prompts for MBPP (Mostly Basic Python Problems)

from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_smith.orchestrator.base_orchestrator import BaseOrchestrator
from agent_smith.orchestrator.models import (
    MBPPTaskInput,
    SolutionOutput,
    StepMetrics,
)

from agent_smith.sandbox.runner import SandboxRunner


class MBPPOrchestrator(BaseOrchestrator):
    """
    A specialized orchestrator for handling MBPP tasks.
    """

    def __init__(
        self,
        model_name: str,
        providers_config: Optional[List[Dict[str, Any]]] = None,
        default_provider_url: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        max_iterations: int = 10,
    ):

        system_prompt = (
            "You are an expert Python developer specialized in solving "
            "algorithmic problems.\n"
            "Your task is to write python code that solves the given problem "
            "and pass all tests.\n"
            "Available tools: Use the connected MCP tools (such as run_tests) "
            "to validate your implementation.\n"
            "Workflow:\n"
            "1. Think carefully about the algorithm and edge cases.\n"
            "2. Write executable Python code inside a "
            "```python ... ``` block.\n"
            "3. Observe the test results from the sandbox.\n"
            "4. When the solution is complete and verified, call "
            "final_answer(your_solution_code) passing the solution code as a "
            "string.\n"
            "### Example Interaction:\n"
            "Thought: I need to write a function that adds two numbers. "
            "Let's check the test cases first using "
            "run_tests(code, test_list).\n"
            "```python\n"
            "code = '''def add(a, b):\n    return a - b'''\n"
            "tests = ['assert add(2, 3) == 5']\n"
            "result = run_tests(code, tests)\n"
            "print(result)\n"
            "```\n"
            "Observation from sandbox:\n"
            "Stdout:\nTests failed: expected 5, got -1\n"
            "...\n"
            "Thought: Ah, I used '-' instead of '+'. "
            "Let me fix the code string, verify it, and pass the code as a "
            "string to final_answer().\n"
            "```python\n"
            "solution_code = '''def add(a, b):\n    return a + b'''\n"
            "tests = ['assert add(2, 3) == 5']\n"
            "result = run_tests(solution_code, tests)\n"
            "print(result)\n"
            "final_answer(solution_code)\n"
            "```"
        )

        super().__init__(
            model_name=model_name,
            system_prompt=system_prompt,
            benchmark="mbpp",
            max_iterations=max_iterations,
            providers_config=providers_config,
            default_provider_url=default_provider_url,
            api_keys=api_keys,
            max_input_tokens=6000,
            max_output_tokens=1500,
            max_time_seconds=120.0,
        )

    def solve_task(self, task_input: MBPPTaskInput) -> SolutionOutput:
        """
        Prepare the initial prompt based on the input from the MBPP task
        and execute the base orchestrator loop.
        """
        initial_prompt = (
            f"Problem Definition:\n{task_input.task_definition}\n\n"
            f"Function Signature / "
            f"Template:\n{task_input.function_definition}\n\n"
            f"Test imports: {task_input.test_imports}\n"
            f"Tests to pass:\n" + "\n".join(task_input.test_list)
        )
        mcp_stdio_cmd = "python mcp_tools_mbpp.py"
        base_system_prompt = self.system_prompt
        effective_system_prompt = base_system_prompt

        try:
            with SandboxRunner(mcp_stdio=mcp_stdio_cmd) as runner:
                self.sandbox_runner = runner
                effective_system_prompt = (
                    f"{base_system_prompt}\n\n"
                    f"### Available functions:\n{runner.manual}"
                )
                self.system_prompt = effective_system_prompt
                return self.run(
                    task_id=str(task_input.task_id),
                    initial_task_prompt=initial_prompt,
                    step_metrics_class=StepMetrics,
                    solution_output_class=SolutionOutput,
                )
        except Exception as e:
            return SolutionOutput(
                task_id=str(task_input.task_id),
                benchmark=self.benchmark,
                success=False,
                solution="",
                iterations=0,
                total_requests=0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_time_seconds=0.0,
                steps=[],
                system_prompt=effective_system_prompt,
                error=f"MCPConnectionOrSandboxError: {str(e)}",
                timestamp=(
                    datetime.now().isoformat()
                    if "datetime" in globals()
                    else ""
                ),
            )
        finally:
            self.system_prompt = base_system_prompt
