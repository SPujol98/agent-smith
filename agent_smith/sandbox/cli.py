import sys
from pathlib import Path
from agent_smith.config import SandboxConfig

DEFAULT_TEMPLATE = Path("sandbox_template.json")


def load_configuration() -> SandboxConfig:
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1])
        return SandboxConfig.from_file(target_path)
    if DEFAULT_TEMPLATE.exists():
        return SandboxConfig.from_file(DEFAULT_TEMPLATE)
    config = SandboxConfig()
    config.save_template(DEFAULT_TEMPLATE)
    return config


def main() -> None:
    config = load_configuration()
    print("=== Agent Smith Sandbox ===")
    print(f"Memoria máxima: {config.max_memory_mb} MB")
    print(f"Timeout: {config.max_execution_time_seconds}s")
    print(f"Imports permitidos: {len(config.authorized_imports)} reglas")
    print(f"Directorios permitidos: {config.allowed_directories}")


if __name__ == "__main__":
    main()
