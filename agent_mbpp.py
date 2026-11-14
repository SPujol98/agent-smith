# Executable CLI script (calls MBPP logic)
import io
import json
import os
import sys
from pathlib import Path

import fire
from dotenv import load_dotenv

from agent_smith.evaluation_logging import save_evaluation_logs
from agent_smith.orchestrator.mbpp import MBPPOrchestrator
from agent_smith.orchestrator.models import MBPPTaskInput

load_dotenv()


def main(
    task_file: str, output: str, model_name: str, provider_url: str = ""
) -> None:
    """
    CLI for running the standalone agent on MBPP tasks using Python Fire,
    including automatic evaluation logging.
    """
    task_path = Path(task_file)
    if not task_path.exists():
        raise FileNotFoundError(
            f"The assignment file was not found at: {task_file}"
        )

    with open(task_path, "r", encoding="utf-8") as f:
        task_raw_data = json.load(f)

    task_input = MBPPTaskInput(**task_raw_data)
    raw_keys = os.getenv("LLM_API_KEYS", os.getenv("OPENAI_API_KEY", ""))
    api_keys_list = [k.strip() for k in raw_keys.split(",") if k.strip()]

    orchestrator = MBPPOrchestrator(
        model_name=model_name,
        default_provider_url=provider_url if provider_url else None,
        api_keys=api_keys_list if api_keys_list else None,
    )

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    solution_output = None
    try:
        solution_output = orchestrator.solve_task(task_input)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        stdout_text = captured_stdout.getvalue()
        stderr_text = captured_stderr.getvalue()

        print(stdout_text, end="")
        print(stderr_text, end="", file=sys.stderr)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    solution_json_str = solution_output.model_dump_json(indent=2)
    output_path.write_text(solution_json_str, encoding="utf-8")

    save_evaluation_logs(
        benchmark="mbpp",
        task_id=str(task_input.task_id),
        task_raw_data=task_raw_data,
        solution_output=solution_output,
        stdout_content=stdout_text,
        stderr_content=stderr_text,
    )

    print(f"[Success] MBPP Task '{task_input.task_id}' processed correctly.")
    print(f"Solution exported to: {output}")


if __name__ == "__main__":
    fire.Fire(main)
