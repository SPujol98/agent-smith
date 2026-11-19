import os
import time
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


class LLMProviderManager:
    def __init__(
        self,
        model_name: str,
        default_provider_url: Optional[str] = None,
        providers_config: Optional[List[Dict[str, Any]]] = None,
        api_keys: Optional[List[str]] = None,
    ) -> None:
        self._explicit_model = model_name
        self.model_name = model_name
        self.default_provider_url = default_provider_url

        if providers_config:
            self.providers = providers_config
        else:
            self.providers = [
                {
                    "url": default_provider_url,
                    "keys": (
                        api_keys
                        if api_keys
                        else [os.getenv("OPENAI_API_KEYS", "dummy-key")]
                    ),
                }
            ]
        self._current_provider_index = 0
        self._current_key_index = 0
        first_default = self.providers[0].get("default_model")
        if not self.model_name and first_default:
            self.model_name = first_default

    def _get_active_client(self) -> OpenAI:
        prov = self.providers[self._current_provider_index]
        current_url = prov.get("url")
        keys = prov.get("keys", ["dummy"])
        current_key = keys[self._current_key_index % len(keys)]
        return OpenAI(
            base_url=current_url if current_url else None, api_key=current_key
        )

    def rotate_key_or_provider(self) -> None:
        prov = self.providers[self._current_provider_index]
        keys = prov.get("keys", [])
        self._current_key_index += 1

        if self._current_key_index >= len(keys):
            self._current_key_index = 0
            old_prov_idx = self._current_provider_index
            self._current_provider_index = (
                self._current_provider_index + 1
            ) % len(self.providers)
            new_prov = self.providers[self._current_provider_index]
            new_default_model = new_prov.get("default_model")
            if new_default_model:
                self.model_name = new_default_model
            else:
                self.model_name = self._explicit_model
            print(
                "[Provider Fallback] Switching index providers "
                f"{old_prov_idx} to {self._current_provider_index}"
            )
        else:
            print("[Token Rotation] Rotating to the next API key.")

    def call_llm(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        max_attempts = sum(len(p.get("keys", [])) for p in self.providers) * 2
        attempts = 0
        backoff_factor = 2
        start_time = time.time()
        errors_history: List[str] = []

        while attempts < max_attempts:
            try:
                client = self._get_active_client()
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=cast(list[ChatCompletionMessageParam], messages),
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
                active_prov = self.providers[self._current_provider_index]
                prov_url = active_prov.get("url") or "default_openai"
                error_summary = (
                    f"[attempt {attempts}/{max_attempts} | "
                    f"prov={self._current_provider_index} ({prov_url}) | "
                    f"model={self.model_name}] {e}"
                )
                errors_history.append(error_summary)
                print(
                    "[Warning] LLM error "
                    f"(Attempt {attempts}/{max_attempts}): {e}"
                )
                self.rotate_key_or_provider()
                if attempts >= max_attempts:
                    first_err = errors_history[0]
                    last_err = errors_history[-1]
                    raise RuntimeError(
                        "Total failure: All providers exhausted. "
                        f"First error: {first_err} || Last error: {last_err}"
                    )
                time.sleep(backoff_factor ** (attempts % 3))
