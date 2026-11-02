# Executable CLI script (calls MBPP logic)
# Instan la clase: orchestrator = MBPPOrchestrator(model_name, provider_url)
import json
import fire
from pathlib import Path
from agent_smith.orchestrator.models import MBPPTaskInput
from agent_smith.orchestrator.mbpp import MBPPOrchestrator


def main(
        task_file: str,
        output: str,
        model_name: str,
        provider_url: str = None
):
    """
    CLI for running the standalone agent on MBPP tasks using Python Fire.
    """
    task_path = Path(task_file)
    if not task_path.exists():
        raise FileNotFoundError(
            f"The assignment file was not found at: {task_file}"
        )

    with open(task_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    task_input = MBPPTaskInput(**task_data)

    orchestrator = MBPPOrchestrator(
            model_name=model_name,
            default_provider_url=provider_url
        )

    solution_output = orchestrator.solve_task(task_input)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(solution_output.model_dump_json(indent=2))

    print(
        f"[Success] MBPP Assignment '{task_input.task_id}' "
        "processed correctly."
    )
    print(f"Solution exported to: {output}")


if __name__ == "__main__":
    fire.Fire(main)
