# Generic Agent Loop (Thought -> Code -> Observation)
import time
from abc import ABC
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_smith.orchestrator.models import SolutionOutput, StepMetrics
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.runner import SandboxRunner
from agent_smith.orchestrator.extraction import extract_code
from agent_smith.orchestrator.llm_manager import LLMProviderManager


class BaseOrchestrator(ABC):
    def __init__(
        self,
        model_name: str,
        system_prompt: str,
        benchmark: str,
        max_iterations: int = 10,
        providers_config: Optional[List[Dict[str, Any]]] = None,
        default_provider_url: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        max_input_tokens: int = 100000,
        max_output_tokens: int = 10000,
        max_time_seconds: float = 300.0,
    ):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.benchmark = benchmark
        self.max_iterations = max_iterations
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_time_seconds = max_time_seconds

        self.llm_manager = LLMProviderManager(
            model_name=model_name,
            default_provider_url=default_provider_url,
            providers_config=providers_config,
            api_keys=api_keys,
        )
        self.sandbox_runner = SandboxRunner()

    def run(
        self,
        task_id: str,
        initial_task_prompt: str,
        step_metrics_class: StepMetrics,
        solution_output_class: SolutionOutput,
    ) -> SolutionOutput:

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": initial_task_prompt},
        ]

        steps = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_requests = 0
        start_time = time.time()

        success = False
        final_solution = ""
        error_message = None

        for iteration in range(1, self.max_iterations + 1):
            try:
                elapsed_time = time.time() - start_time
                if elapsed_time >= self.max_time_seconds:
                    error_message = f"TimeLimitExceeded: {self.max_time_seconds}s exceeded."
                    break

                if total_input_tokens >= self.max_input_tokens:
                    error_message = f"TokenBudgetExceeded: Input tokens limit exceeded."
                    break

                llm_response = self.llm_manager.call_llm(messages)
                retries_count = llm_response.get("retries", 0)
                total_requests += 1 + retries_count

                in_tokens = llm_response.get("input_tokens", 0)
                out_tokens = llm_response.get("output_tokens", 0)
                total_input_tokens += in_tokens
                total_output_tokens += out_tokens

                if total_output_tokens >= self.max_output_tokens:
                    error_message = f"TokenBudgetExceeded: Output tokens limit exceeded."
                    break

                raw_output = llm_response.get("text", "")
                code_to_run = extract_code(raw_output)

                execution_result: ExecutionResult = self.sandbox_runner.run(code_to_run)

                sandbox_output_combined = (
                    f"Stdout:\n{execution_result.stdout}\n"
                    f"Stderr:\n{execution_result.stderr}"
                )
                if execution_result.error:
                    sandbox_output_combined += f"\nError:\n{execution_result.error}"

                active_api_url = (
                    llm_response.get("active_url")
                    or self.llm_manager.default_provider_url
                    or "https://api.openai.com/v1"
                )

                step_metric = step_metrics_class(
                    step=iteration,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    request_time_ms=llm_response.get("latency_ms", 0.0),
                    api_url=active_api_url,
                    model_name=self.model_name,
                    llm_output=raw_output,
                    sandbox_input=code_to_run,
                    sandbox_output=sandbox_output_combined,
                    retries=retries_count,
                )
                steps.append(step_metric)

                if execution_result.is_finished:
                    success = True
                    final_solution = execution_result.final_answer_value
                    break

                messages.append({"role": "assistant", "content": raw_output})
                messages.append({
                    "role": "user",
                    "content": f"Observation from sandbox:\n{sandbox_output_combined}",
                })

            except Exception as e:
                error_message = str(e)
                break

        total_time = time.time() - start_time

        return solution_output_class(
            task_id=task_id,
            benchmark=self.benchmark,
            success=success,
            solution=final_solution,
            iterations=len(steps),
            total_requests=total_requests,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_time_seconds=total_time,
            steps=steps,
            system_prompt=self.system_prompt,
            error=error_message,
            timestamp=datetime.now().isoformat(),
        )