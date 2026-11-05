# Specific logic and prompts for SWE-bench
# from base import BaseOrchestrator
import subprocess
import uuid
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

    def _start_docker_container(self, image_name: str, container_name: str):
        """Start the Docker container in the background for the task."""

        print(
            f"[Docker] Starting a container {container_name} "
            f"with an Image {image_name}..."
        )

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            image_name,
            "sleep",
            "infinity"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Error starting the Docker container: {result.stderr}"
            )
        print(f"[Docker] Container {container_name} started successfully.")

    def _cleanup_docker_container(self, container_name: str):
        """Required: Clean and empty the trash can when you're done."""

        print(f"[Docker] Cleaning and Deleting a Container {container_name}")

        cmd = [
            "docker",
            "rm",
            "-f",
            container_name
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"[Warning] The container could not be cleanly "
                f"deleted {container_name}: {result.stderr}"
            )
        else:
            print(f"[Docker] Container {container_name} successfully deleted.")

    def solve_task(self, task_input: SWEBenchTaskInput) -> SolutionOutput:
        """
        Manages the Docker lifecycle, sets up the initial prompt,
        and runs the orchestrator loop.
        """

        safe_id = (
            str(task_input.instance_id).replace("/", "_").replace(":", "_")
        )
        container_name = f"agent_smith_{safe_id}_{uuid.uuid4().hex[:6]}"

        image_name = getattr(task_input, "image_name", "python:3.10-slim")

        try:
            self._start_docker_container(image_name, container_name)

            hints = (
                task_input.hints_text
                if task_input.hints_text
                else "None provided."
            )

            initial_prompt = (
                f"Repository: {task_input.repo}\n"
                f"Instance ID: {task_input.instance_id}\n"
                f"Docker Container: {container_name}\n\n"
                f"### Problem Statement:\n{task_input.problem_statement}\n\n"
                f"### Hints:\n{hints}\n\n"
                f"### Instructions:\n"
                f"Explore files under /testbed/,locate the bug, write the fix,"
                f"and return the resulting git patch (diff) via final_answer()"
                f"`git -c core.fileMode=false diff`."
            )

            solution_output = self.run(
                task_id=task_input.instance_id,
                initial_task_prompt=initial_prompt,
                step_metrics_class=StepMetrics,
                solution_output_class=SolutionOutput
            )

            return solution_output

        finally:
            self._cleanup_docker_container(container_name)
