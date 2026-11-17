"""Authorized modules must not lead to unauthorized ones."""

import pytest

from agent_smith.sandbox.runner import SandboxRunner


@pytest.mark.parametrize(
    "code",
    [
        "import random\nrandom._os.getcwd()",
        "from random import _os",
        "import typing\ntyping.sys.modules['os']",
        "import json\njson.codecs.sys",
        "import re\nre.enum.sys",
        "import collections\ncollections.sys",
    ],
)
def test_authorized_module_does_not_expose_other_modules(code: str) -> None:
    """Private names and unauthorized modules are not in the copy."""
    # Arrange
    runner = SandboxRunner()

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert "AttributeError" in result.error or "ImportError" in result.error


def test_authorized_modules_still_work() -> None:
    """Public names and authorized submodules are kept."""
    # Arrange
    runner = SandboxRunner()
    code = (
        "import collections.abc\n"
        "import json\n"
        "from math import sqrt\n"
        "from typing import List\n"
        "values: List[float] = [sqrt(16)]\n"
        "is_seq = isinstance(values, collections.abc.Sequence)\n"
        "text = json.dumps(values)\n"
    )

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is True, result.error
    assert result.result_env["is_seq"] is True
    assert result.result_env["text"] == "[4.0]"
