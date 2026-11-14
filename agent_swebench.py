# Executable CLI script (calls the SWE-bench logic)
import io
import json
import sys
from pathlib import Path

import fire
from dotenv import load_dotenv

from agent_smith.orchestrator.config_api import (
    get_providers_config,
    get_default_model
)
from agent_smith.evaluation_logging import save_evaluation_logs
from agent_smith.orchestrator.models import SWEBenchTaskInput
from agent_smith.orchestrator.swebench import SWEBenchOrchestrator

load_dotenv()


def main(
    task_file: str, output: str, model_name: str = "", provider_url: str = ""
) -> None:
    """
    CLI for running the standalone agent on SWE-bench tasks using Python Fire,
    including automatic evaluation logging and multi-provider configuration.
    """

    task_path = Path(task_file)
    if not task_path.exists():
        raise FileNotFoundError(
            f"The assignment file was not found at: {task_file}"
        )

    with open(task_path, "r", encoding="utf-8") as f:
        task_raw_data = json.load(f)

    task_input = SWEBenchTaskInput(**task_raw_data)

    providers_config = get_providers_config()

    if not model_name:
        model_name = get_default_model(0)

    orchestrator = SWEBenchOrchestrator(
        model_name=model_name,
        providers_config=providers_config if providers_config else None,
        default_provider_url=provider_url if provider_url else None,
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
        benchmark="swebench",
        task_id=str(task_input.instance_id),
        task_raw_data=task_raw_data,
        solution_output=solution_output,
        stdout_content=stdout_text,
        stderr_content=stderr_text,
    )

    print(
        f"[Success] SWE-bench Assignment '{task_input.instance_id}' "
        "processed correctly."
    )
    print(f"Solution exported to: {output}")


if __name__ == "__main__":
    fire.Fire(main)
