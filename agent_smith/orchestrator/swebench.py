# Specific logic and prompts for SWE-bench
# from base import BaseOrchestrator
import subprocess
import uuid
from agent_smith.orchestrator.base_orchestrator import BaseOrchestrator
from agent_smith.orchestrator.models import (
    SWEBenchTaskInput,
    SolutionOutput,
    StepMetrics
)
from datetime import datetime
from typing import Optional, List, Dict, Any
from agent_smith.sandbox.runner import SandboxRunner


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
            "### Example Interaction:\n"
            "Thought: I need to inspect the files under /testbed/ to find "
            "where the bug resides.\n"
            "```python\n"
            "content = read_file('/testbed/math_utils.py')\n"
            "print(content)\n"
            "```\n"
            "Observation from sandbox:\n"
            "Stdout:\n"
            "def divide(a, b):\n"
            "    return a / b  # Bug: no zero division check\n"
            "...\n"
            "Thought: I found the issue. I will fix the bug in the file "
            "and then verify it.\n"
            "```python\n"
            "edit_file('/testbed/math_utils.py', old_content='return a / b', "
            "new_content='if b == 0: raise ValueError(\"Zero division\"); "
            "return a / b')\n"
            "print('Fixed successfully')\n"
            "```\n"
            "Observation from sandbox:\n"
            "Stdout:\n"
            "Fixed successfully\n"
            "...\n"
            "Thought: The fix is applied and verified."
            "Now I will get the patch and finish.\n"
            "```python\n"
            "patch = get_patch()\n"
            "final_answer(patch)\n"
            "```"
        )

        super().__init__(
            model_name=model_name,
            system_prompt=system_prompt,
            benchmark="swebench",
            max_iterations=max_iterations,
            providers_config=providers_config,
            default_provider_url=default_provider_url,
            api_keys=api_keys,
            max_input_tokens=300000,
            max_output_tokens=10000,
            max_time_seconds=900.0,
        )

    def _start_docker_container(self, docker_image: str, container_name: str):
        """Start the Docker container in the background for the task."""

        print(
            f"[Docker] Starting a container {container_name} "
            f"with an Image {docker_image}..."
        )

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            docker_image,
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

        docker_image = getattr(task_input, "docker_image", "python:3.10-slim")

        try:
            self._start_docker_container(docker_image, container_name)

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
            mcp_stdio_cmd = "python mcp_tools_swebench.py"

            with SandboxRunner(
                mcp_stdio=mcp_stdio_cmd,
                mcp_env={"SWE_CONTAINER": container_name},
            ) as runner:
                self.sandbox_runner = runner
                self.system_prompt += (
                    f"\n\n### Available functions:\n{runner.manual}"
                )

                return self.run(
                    task_id=task_input.instance_id,
                    initial_task_prompt=initial_prompt,
                    step_metrics_class=StepMetrics,
                    solution_output_class=SolutionOutput,
                )
        except Exception as e:
            return SolutionOutput(
                task_id=str(task_input.instance_id),
                benchmark=self.benchmark,
                success=False,
                solution="",
                iterations=0,
                total_requests=0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_time_seconds=0.0,
                steps=[],
                system_prompt=self.system_prompt,
                error=f"MCPConnectionOrSandboxError: {str(e)}",
                timestamp=(
                    datetime.now().isoformat()
                    if "datetime" in globals()
                    else ""
                ),
            )
        finally:
            self._cleanup_docker_container(container_name)
