# Specific Logic and Prompts for MBPP (Mostly Basic Python Problems)

from agent_smith.orchestrator.base_orchestrator import BaseOrchestrator
from agent_smith.orchestrator.models import (
    MBPPTaskInput,
    SolutionOutput,
    StepMetrics
)
from typing import Optional, List, Dict, Any


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
            "final_answer(your_solution_code).\n"
        )

        super().__init__(
            model_name=model_name,
            system_prompt=system_prompt,
            benchmark="mbpp",
            max_iterations=max_iterations,
            providers_config=providers_config,
            default_provider_url=default_provider_url,
            api_keys=api_keys
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

        return self.run(
            task_id=str(task_input.task_id),
            initial_task_prompt=initial_prompt,
            step_metrics_class=StepMetrics,
            solution_output_class=SolutionOutput
        )
