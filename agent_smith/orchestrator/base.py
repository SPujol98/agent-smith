# Generic Agent Loop (Thought -> Code -> Observation)
import time
from datetime import datetime
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict, Any, Type
from sandbox.runner import SandboxRunner
from sandbox.result import ExecutionResult


class BaseOrchestrator(ABC):

    def __init__(
            self,
            model_name: str,
            provider_url: str,
            system_prompt: str,
            benchmark: str,
            max_iterations: int = 10,
    ):
        self.model_name = model_name
        self.provider_url = provider_url
        self.system_prompt = system_prompt
        self.benchmark = benchmark
        self.max_iterations = max_iterations

        self.sandbox_runner = SandboxRunner()

    @abstractmethod
    def _call_llm(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _extract_code(self, llm_output: str) -> str:
        pass

    def run(
            self,
            task_id: str,
            initial_task_prompt: str,
            step_metrics_class: Type[BaseModel],
            solution_output_class: Type[BaseModel]
    ) -> BaseModel:

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
                    self.sandbox_runner.execute(code_to_run)
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
                    sandbox_output=execution_result.output,
                    retries=retries_count
                )
                steps.append(step_metric)

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


# Anotaciones de Sabri:
'''
_call_llm Debe retornar un dict que incluya:
    - text: str (respuesta cruda)
    - input_tokens: int
    - output_tokens: int
    - request_time_ms: float
    - retries: int (intentos necesarios)
'''
"""
=============================================================================
GENERIC AGENT LOOP (Thought -> Code -> Observation) EN EL MÉTODO .run()
=============================================================================

[ Inicio de .run() ] -> Prepara historial y contadores
       │
       ▼
 ┌─── LOOP (Hasta max_iterations o final_answer)
 │     │
 │     ├─► 1. THOUGHT (Pensamiento)
 │     │     └─► Envía historial al LLM y recibe la respuesta con código.
 |     |         Llamada al _call_llm
 │     │
 │     ├─► 2. CODE (Acción)
 │     │     └─► Extrae el código y lo ejecuta en el Sandbox.
 |     |         Llamada al _extract_code
 │     │
 │     ├─► 3. OBSERVATION (Observación)
 │     │     └─► Captura el resultado del sandbox y lo añade al historial.
 │     │
 │     ├─► ¿Llamó a final_answer()?
 │     │     ├── SÍ ──► Éxito (Termina el bucle)
 │     │     └── NO  ──► Repite el ciclo con la nueva observación
 │     │
 └─── ┘
       │
       ▼
 [ Fin de .run() ] -> Retorna el objeto SolutionOutput con todas las métricas
=============================================================================

Observation: Cuando el sandbox devuelve el resultado
(éxito, error, salida por pantalla) y lo guarda en el historial para la
siguiente vuelta:
messages.append(
{"role": "user", "content": f"Observation...\n{execution_result.output}"})
)
"""
