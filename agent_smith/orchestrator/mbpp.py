# Specific Logic and Prompts for MBPP (Mostly Basic Python Problems)
from base import BaseOrchestrator


class MBPPOrchestrator(BaseOrchestrator):
    def __init__(
            self,
            model_name: str,
            provider_url: str,
            max_iterations: int = 10,
    ):

        system_prompt = (
            "You are an expert Python programmer and problem solver. "
            "Your task is to write clean, correct Python code to solve "
            "algorithmic problems. You are interacting with an execution "
            "sandbox. When you have verified your solution, call "
            "final_answer(your_solution_code)."
        )

        super.__init__(
            model_name=model_name,
            provider_url=provider_url,
            system_prompt=system_prompt,
            benchmark="mbpp",
            max_iterations=max_iterations,
        )

