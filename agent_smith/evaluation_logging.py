# Evaluation logging structure
# Evaluation of AI agents: traceability (auditing), reproducibility,
# and isolation of the execution environment.

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def save_evaluation_logs(
    benchmark: str,
    task_id: str,
    task_raw_data: dict,
    solution_output: Any,
    stdout_content: str = "",
    stderr_content: str = ""
) -> Path:
    """
    Store the structured evaluation logs under:
    ./evaluations/TYPE/YYYY-MM-DD_HH-MM-SS/task_id/
    """
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    eval_dir = Path("evaluations") / benchmark / timestamp_str / str(task_id)
    eval_dir.mkdir(parents=True, exist_ok=True)

    solution_str = (
        solution_output.model_dump_json(indent=2)
        if hasattr(solution_output, "model_dump_json")
        else json.dumps(solution_output, indent=2, ensure_ascii=False)
    )

    files_to_write = {
        "task.json": json.dumps(task_raw_data, indent=2, ensure_ascii=False),
        "solution.json": solution_str,
        "stdout.log": stdout_content,
        "stderr.log": stderr_content,
    }

    for filename, content in files_to_write.items():
        (eval_dir / filename).write_text(content, encoding="utf-8")

    print(f"[Evaluation Logger] Logs successfully saved to: {eval_dir}")
    return eval_dir
