# Everything related to the multikey, retry, and OpenAI client can be encapsulated in a helper class
# agent_smith/orchestrator/llm_manager.py
import os
import time
from typing import Any, Dict, List, Optional
from openai import OpenAI


class LLMProviderManager:
    def __init__(
        self,
        model_name: str,
        default_provider_url: Optional[str] = None,
        providers_config: Optional[List[Dict[str, Any]]] = None,
        api_keys: Optional[List[str]] = None,
    ):
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
                        else [os.getenv("OPENAI_API_KEY", "dummy-key")]
                    ),
                }
            ]
        self._current_provider_index = 0
        self._current_key_index = 0

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
                print(f"[Warning] LLM error (Attempt {attempts}/{max_attempts}): {e}")
                self.rotate_key_or_provider()
                if attempts >= max_attempts:
                    raise RuntimeError(
                        f"Total failure: All providers exhausted: {str(e)}"
                    )
                time.sleep(backoff_factor ** (attempts % 3))