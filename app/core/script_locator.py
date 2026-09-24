"""Resolve pasted paths and discover entry-point scripts in one directory."""

import os
from pathlib import Path
from typing import List, Optional, Sequence


def normalize_path_text(text: str) -> str:
    """Normalize whitespace, surrounding quotes, and environment variables."""
    value = text.strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return os.path.expandvars(os.path.expanduser(value))


def list_python_scripts(directory: str) -> List[Path]:
    """List only the immediate directory's Python files in display order."""
    path = Path(directory)
    if not path.is_dir():
        return []

    scripts = [
        child.resolve()
        for child in path.iterdir()
        if child.is_file() and child.suffix.lower() == ".py"
    ]
    return sorted(
        scripts,
        key=lambda item: (
            item.name.lower() != "main.py",
            "main" not in item.stem.lower(),
            item.name.lower(),
        ),
    )


def find_preferred_script(scripts: Sequence[Path]) -> Optional[Path]:
    """Select an unambiguous main-style script; otherwise require user choice."""
    exact_main = [script for script in scripts if script.name.lower() == "main.py"]
    if exact_main:
        return exact_main[0]

    main_related = [script for script in scripts if "main" in script.stem.lower()]
    if len(main_related) == 1:
        return main_related[0]
    return None
