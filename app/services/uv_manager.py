"""uv availability checks and run-command construction."""

import shutil
from typing import List, Sequence

from ..core.dependency_analyzer import normalize_dep_text


def is_uv_available() -> bool:
    """Return whether the uv executable is available on PATH."""
    return shutil.which("uv") is not None


def build_uv_dependency_args(dependencies_text: str) -> List[str]:
    args = []
    for dependency in normalize_dep_text(dependencies_text):
        args.extend(["--with", dependency])
    return args


def build_uv_run_command(
    python_version: str,
    dependencies_text: str,
    command_args: Sequence[str],
    extra_packages: Sequence[str] = (),
) -> List[str]:
    """Build a complete uv run command shared by run and build workflows."""
    command = ["uv", "run", "--python", python_version]
    for package in extra_packages:
        command.extend(["--with", package])
    command.extend(build_uv_dependency_args(dependencies_text))
    command.extend(command_args)
    return command


def build_run_command(script_path: str, python_version: str, dependencies_text: str) -> List[str]:
    return build_uv_run_command(
        python_version=python_version,
        dependencies_text=dependencies_text,
        command_args=[script_path],
    )
