# Generic Agent Loop (Thought -> Code -> Observation)
import time
import os
import json
import re
from openai import OpenAI
from datetime import datetime
from abc import ABC
from typing import List, Dict, Any, Optional
from agent_smith.sandbox.runner import SandboxRunner
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.orchestrator.models import SolutionOutput, StepMetrics


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
    ):
        self.model_name = model_name
        self.provider_url = default_provider_url
        self.system_prompt = system_prompt
        self.benchmark = benchmark
        self.max_iterations = max_iterations
        if providers_config:
            self.providers = providers_config
        else:
            self.providers = [{
                "url": default_provider_url,
                "keys": (api_keys if
                         api_keys
                         else [os.getenv("OPENAI_API_KEY", "dummy-key")])
            }]
        self._current_provider_index = 0
        self._current_key_index = 0
        self.sandbox_runner = SandboxRunner()

    def _get_active_client(self) -> OpenAI:
        """
        Get the OpenAI client by specifying the current provider and token.
        """
        prov = self.providers[self._current_provider_index]
        current_url = prov.get("url")
        keys = prov.get("keys", ["dummy"])
        current_key = keys[self._current_key_index % len(keys)]

        return OpenAI(
            base_url=current_url if current_url else None,
            api_key=current_key
        )

    def _rotate_key_or_provider(self):
        """
        Rotation and Fallback Strategy:
        1. Attempt to rotate to the next token from the current provider.
        2. If this provider's keys have already run out,
            fall back to the next provider.
        """
        prov = self.providers[self._current_provider_index]
        keys = prov.get("keys", [])

        self._current_key_index += 1

        if self._current_key_index >= len(keys):
            self._current_key_index = 0
            old_prov_idx = self._current_provider_index
            self._current_provider_index = (
                (self._current_provider_index + 1) % len(self.providers)
            )
            print("[Provider Fallback] Switching index providers"
                  f" {old_prov_idx} to {self._current_provider_index}")
        else:
            print("[Token Rotation] Rotating to the next API key "
                  "from the current provider.")

    def _call_llm(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Call to the LLM with full support for Multi-Key,
        Multi-Provider, and Fallback.
        """
        max_attempts = sum(len(p.get("keys", [])) for p in self.providers) * 2
        attempts = 0
        backoff_factor = 2

        start_time = time.time()

        while attempts < max_attempts:
            try:
                client = self._get_active_client()

                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.2,
                    stop=["</end_code>", "<end_code>", "</tool_call>"],
                )

                latency_ms = (time.time() - start_time) * 1000
                text_output = response.choices[0].message.content or ""

                usage = response.usage
                input_tokens = usage.prompt_tokens if usage else 0
                output_tokens = usage.completion_tokens if usage else 0

                active_prov = self.providers[self._current_provider_index]

                return {
                    "text": text_output,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "retries": attempts,
                    "active_url": active_prov.get("url"),
                }

            except Exception as e:
                attempts += 1
                print(
                    "[Warning] LLM error "
                    f"(Attempt {attempts}/{max_attempts}): {e}")
                self._rotate_key_or_provider()
                if attempts >= max_attempts:
                    raise RuntimeError(
                        "Total failure: All available tokens and providers "
                        f"have been exhausted: {str(e)}")
                time.sleep(backoff_factor ** (attempts % 3))

    def _extract_code(self, llm_output: str) -> str:
        """A universal method for extracting code
        blocks from the LLM's response,

        handling multiple model output formats
        (Python blocks, XML, JSON/Hermes,ReAct)
        """

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
                args_str = ", ".join(
                    f"{k}={v!r}" for k, v in args.items()
                )
                return f"result = {name}({args_str})\nprint(result)"
            except Exception:
                pass

        invoke_pattern = (
            r'<invoke\s+name=["\'](.*?)["\']>(.*?)</invoke>'
        )
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

        return llm_output.strip()

    def run(
            self,
            task_id: str,
            initial_task_prompt: str,
            step_metrics_class: StepMetrics,
            solution_output_class: SolutionOutput
    ) -> SolutionOutput:

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": initial_task_prompt}
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

                llm_response = self._call_llm(messages)
                total_requests += 1

                in_tokens = llm_response.get("input_tokens", 0)
                out_tokens = llm_response.get("output_tokens", 0)
                total_input_tokens += in_tokens
                total_output_tokens += out_tokens
                raw_output = llm_response.get("text", "")
                retries_count = llm_response.get("retries", 0)

                code_to_run = self._extract_code(raw_output)

                execution_result: ExecutionResult = (
                    self.sandbox_runner.run(code_to_run)
                )

                sandbox_output_combined = (
                    f"Stdout:\n{execution_result.stdout}\n"
                    f"Stderr:\n{execution_result.stderr}"
                )

                if execution_result.error:
                    sandbox_output_combined += (
                        f"\nError:\n{execution_result.error}"
                    )

                step_metric = step_metrics_class(
                    step=iteration,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    request_time_ms=llm_response.get("latency_ms", 0.0),
                    api_url=self.provider_url,
                    model_name=self.model_name,
                    llm_output=raw_output,
                    sandbox_input=code_to_run,
                    sandbox_output=sandbox_output_combined,
                    retries=retries_count
                )
                steps.append(step_metric)
# pendiente finer_answer de sergio para terminar de configurar la salida
                if execution_result.is_finished:
                    success = True
                    final_solution = execution_result.final_answer_value
                    break

                messages.append({"role": "assistant", "content": raw_output})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Observation from sandbox:\n{execution_result.output}"
                    )
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
            timestamp=datetime.now().isoformat()
        )
