from typing import List
from pydantic import BaseModel, Field, ValidationError
from pathlib import Path


class SandboxConfig(BaseModel):
    """Sandbox configuration for student solutions.
    Uses allowlist approach: only imports in authorized_imports are allowed.
    Everything else is blocked by default.
    """
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*",
        "collections", "collections.*",
        "itertools", "re", "json",
        "typing", "typing.*",
        "functools", "operator",
        "heapq", "bisect", "copy",
        "string", "random",
        "datetime", "datetime.*",
        "array", "cmath",
    ])
    allowed_directories: List[str] = Field(default_factory=lambda: [
        "/testbed", "/tmp/agent"
    ])
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512

    @classmethod
    def from_file(cls, filepath: str | Path) -> "SandboxConfig":
        try:
            content = Path(filepath).read_text(encoding="utf-8")
            return cls.model_validate_json(content)
        except FileNotFoundError:
            raise FileNotFoundError(f"MISS config file: {filepath}")
        except ValidationError as e:
            raise ValueError("Invalid JSON structure in "
                                  f"{filepath}:\n{e}")

    def save_template(self, filepath: str | Path
                      = "sandbox_template.json") -> None:
        Path(filepath).write_text(self.model_dump_json(indent=2),
                                  encoding="utf-8")
