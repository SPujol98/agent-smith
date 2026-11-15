"""Shared pytest fixtures."""

import os
import stat
from pathlib import Path

import pytest

FAKE_DOCKER = """#!/bin/sh
# Fake `docker exec -i -w DIR CONTAINER CMD...`: log it, run CMD locally.
echo "$@" >> "$FAKE_DOCKER_LOG"
shift                                   # exec
[ "$1" = "-i" ] && shift
[ "$1" = "-w" ] && { cd "$2" 2>/dev/null; shift 2; }
shift                                   # container name
exec "$@"
"""


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a fake `docker` first in PATH; return the file it logs to."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "docker.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.setenv("SWE_CONTAINER", "task-box")
    return log
