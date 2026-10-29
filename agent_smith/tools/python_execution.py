from agent_smith.tools.base import BaseTool
from agent_smith.sandbox.runner import SandboxRunner


class PythonExecutionTool(BaseTool):
    name: str = "python_interpreter"
    description: str = ("Executes Python code inside a secure sandboxed"
                        "environment and returns stdout or error messages.")

    def __init__(self, runner: SandboxRunner) -> None:
        self.runner = runner

    def execute(self, code: str) -> str:  # type: ignore[override]
        result = self.runner.run(code)
        if result.success:
            return (result.stdout if result.stdout.strip()
                    else "Code executed successfully with no output.")
        error_msg = result.error or result.stderr or "Unknown execution error"
        return f"Execution error: {error_msg}"
