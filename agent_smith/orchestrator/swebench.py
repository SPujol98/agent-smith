# Specific logic and prompts for SWE-bench
# from base import BaseOrchestrator

from base_orchestrator import BaseOrchestrator
from models import SWEBenchTaskInput, SolutionOutput, StepMetrics
from typing import Optional, List, Dict, Any


class SWEBenchOrchestrator(BaseOrchestrator):
    """
    Specialized orchestrator for managing SWE-bench tasks
    (resolving actual bugs in repositories and generating Git patches).
    """
    def __init__(
        self,
        model_name: str,
        providers_config: Optional[List[Dict[str, Any]]] = None,
        default_provider_url: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        max_iterations: int = 15,
    ):

        system_prompt = (
            "You are an expert software engineer participating in SWE-bench. "
            "Your task is to fix a real-world GitHub issue in a repository "
            "running inside a Docker environment.\n"
            "Workflow:\n"
            "1. Explore the codebase using available tools or Python commands "
            "to locate the bug.\n"
            "2. Understand the issue described in the problem statement.\n"
            "3. Implement the clean fix.\n"
            "4. Verify your changes.\n"
            "5. When the fix is verified, generate the git patch (diff) using "
            "`git -c core.fileMode=false diff` and finish by calling "
            "final_answer(patch_string).\n"
        )

        super().__init__(
            model_name=model_name,
            system_prompt=system_prompt,
            benchmark="swebench",
            max_iterations=max_iterations,
            providers_config=providers_config,
            default_provider_url=default_provider_url,
            api_keys=api_keys
        )

    def solve_task(self, task_input: SWEBenchTaskInput) -> SolutionOutput:
        """
        Prepare the initial prompt based on the official SWEBenchTaskInput
        and run the base orchestrator's universal loop.
        """
        hints = (
            task_input.hints_text
            if task_input.hints_text
            else "None provided."
        )

        initial_prompt = (
            f"Repository: {task_input.repo}\n"
            f"Instance ID: {task_input.instance_id}\n\n"
            f"### Problem Statement:\n{task_input.problem_statement}\n\n"
            f"### Hints:\n{hints}\n\n"
            f"### Instructions:\n"
            f"Explore files under /testbed/, locate the bug, write the fix, "
            f"and return the resulting git patch (diff) via final_answer()."
        )

        return self.run(
            task_id=task_input.instance_id,
            initial_task_prompt=initial_prompt,
            step_metrics_class=StepMetrics,
            solution_output_class=SolutionOutput
        )
