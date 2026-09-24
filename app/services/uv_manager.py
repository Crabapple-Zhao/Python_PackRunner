"""uv availability checks and run-command construction."""

import shutil
from typing import List

from ..core.dependency_analyzer import normalize_dep_text


def is_uv_available() -> bool:
    """Return whether the uv executable is available on PATH."""
    return shutil.which("uv") is not None


def build_uv_dependency_args(dependencies_text: str) -> List[str]:
    args = []
    for dependency in normalize_dep_text(dependencies_text):
        args.extend(["--with", dependency])
    return args


def build_run_command(script_path: str, python_version: str, dependencies_text: str) -> List[str]:
    return [
        "uv", "run", "--python", python_version,
        *build_uv_dependency_args(dependencies_text), script_path,
    ]
