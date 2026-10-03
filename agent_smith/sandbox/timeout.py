import signal
from types import TracebackType, FrameType
from typing import Any


class TimeoutGuard:
    def __init__(self, seconds: int | None = None) -> None:
        self.seconds = seconds
        self._old_handler: Any = None

    def _handle_timeout(self, signum: int, frame: FrameType | None) -> None:
        raise TimeoutError(f"Execution timed out after {self.seconds} seconds")

    def __enter__(self) -> "TimeoutGuard":
        if self.seconds is not None and self.seconds > 0:
            self._old_handler = signal.signal(
                signal.SIGALRM, self._handle_timeout)
            signal.alarm(self.seconds)
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> None:
        if self.seconds is not None and self.seconds > 0:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, self._old_handler)
