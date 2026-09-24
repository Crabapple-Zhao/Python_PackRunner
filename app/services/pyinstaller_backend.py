"""PyInstaller command, runtime-hook, and artifact-cleanup helpers."""

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence

from ..constants import TK_ICON_RUNTIME_HOOK
from .uv_manager import build_uv_dependency_args


def build_pack_command(
    script_path: str,
    python_version: str,
    dependencies_text: str,
    no_console: bool,
    icon_path: str = "",
) -> List[str]:
    """Build the uv/PyInstaller command without executing it."""
    pyinstaller_args = ["pyinstaller", "--onefile"]
    if no_console:
        pyinstaller_args.append("--noconsole")
    if icon_path:
        pyinstaller_args.append(f"--icon={icon_path}")
    pyinstaller_args.append(script_path)
    return [
        "uv", "run", "--python", python_version, "--with", "pyinstaller",
        *build_uv_dependency_args(dependencies_text), *pyinstaller_args,
    ]


@dataclass(frozen=True)
class CleanupResult:
    removed: List[str]
    warnings: List[str]


def cleanup_pack_artifacts(script_path: str, icon_path: str = "") -> CleanupResult:
    """只清理当前脚本的 build 子目录、空 build 根目录和 spec 文件。"""
    script = Path(script_path).resolve()
    workdir = script.parent
    stem = script.stem
    removed = []
    warnings = []
    build_root = workdir / "build"
    target_build = build_root / stem
    preserve_build = False
    if icon_path:
        try:
            Path(icon_path).resolve().relative_to(target_build.resolve())
            preserve_build = True
        except ValueError:
            pass
    try:
        if preserve_build:
            warnings.append(f"构建目录包含用户选择的 ICO，已保留：{target_build}")
        elif target_build.exists():
            shutil.rmtree(target_build)
            removed.append(str(target_build))
    except Exception as exc:
        warnings.append(f"删除构建目录失败：{target_build} -> {exc}")
    try:
        if build_root.exists() and build_root.is_dir() and not any(build_root.iterdir()):
            build_root.rmdir()
            removed.append(str(build_root))
    except Exception as exc:
        warnings.append(f"删除空 build 目录失败：{build_root} -> {exc}")
    spec_file = workdir / f"{stem}.spec"
    try:
        if spec_file.exists():
            spec_file.unlink()
            removed.append(str(spec_file))
    except Exception as exc:
        warnings.append(f"删除 SPEC 文件失败：{spec_file} -> {exc}")
    return CleanupResult(removed, warnings)


@contextmanager
def tkinter_icon_runtime_hook(
    command: Sequence[str],
    enabled: bool,
    warning_callback: Optional[Callable[[str], None]] = None,
) -> Iterator[List[str]]:
    """在 PyInstaller 命令中临时注入 Tk 窗口图标 runtime hook。"""
    actual_command = list(command)
    if not enabled:
        yield actual_command
        return
    hook_dir = tempfile.TemporaryDirectory(prefix="python_tool_icon_")
    try:
        hook_path = Path(hook_dir.name) / "tk_window_icon.py"
        hook_path.write_text(TK_ICON_RUNTIME_HOOK, encoding="utf-8")
        actual_command[-1:-1] = ["--runtime-hook", str(hook_path)]
        yield actual_command
    finally:
        try:
            hook_dir.cleanup()
        except OSError as exc:
            if warning_callback is not None:
                warning_callback(f"[警告] 图标临时钩子清理失败：{exc}")
