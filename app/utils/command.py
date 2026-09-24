"""Command-line display helpers."""

import os
import shlex
import subprocess
from typing import Sequence


def format_command(command: Sequence[str]) -> str:
    """Format a command for logs without affecting its execution."""
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)
