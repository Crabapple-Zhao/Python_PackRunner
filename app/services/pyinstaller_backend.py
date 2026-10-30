"""PyInstaller command, runtime-hook, and artifact-cleanup helpers."""

import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence

from ..constants import TK_ICON_RESOURCE_NAME, TK_ICON_RUNTIME_HOOK
from .uv_manager import build_uv_run_command
from .resources import (ResourceMapping, validate_resources, resource_is_ignored,
                        resource_files, needs_resource_staging)


def build_pack_command(
    script_path: str,
    python_version: str,
    dependencies_text: str,
    no_console: bool,
    icon_path: str = "",
    resources: Sequence[ResourceMapping] = (),
) -> List[str]:
    """Build the uv/PyInstaller command without executing it."""
    pyinstaller_args = ["pyinstaller", "--onefile"]
    if no_console:
        pyinstaller_args.append("--noconsole")
    if icon_path:
        pyinstaller_args.append(f"--icon={icon_path}")
    for resource in validate_resources(resources, icon_path, script_path):
        pyinstaller_args.extend(["--add-data", f"{resource.source}{os.pathsep}{resource.destination}"])
    pyinstaller_args.append(script_path)
    return build_uv_run_command(
        python_version=python_version,
        dependencies_text=dependencies_text,
        command_args=pyinstaller_args,
        extra_packages=["pyinstaller"],
    )


@dataclass(frozen=True)
class CleanupResult:
    removed: List[str]
    warnings: List[str]


def cleanup_pack_artifacts(script_path: str, icon_path: str = "",
                           resources: Sequence[ResourceMapping] = ()) -> CleanupResult:
    """只清理当前脚本的 build 子目录、空 build 根目录和 spec 文件。"""
    script = Path(script_path).resolve()
    workdir = script.parent
    stem = script.stem
    removed = []
    warnings = []
    build_root = workdir / "build"
    target_build = build_root / stem
    source_paths = [Path(item.source).resolve() for item in resources]

    def contains(parent, child):
        return parent == child or parent in child.parents

    def protected(target):
        return any(contains(target, source) or (source.is_dir() and contains(source, target)
                                               and not resource_is_ignored(source, target, script_path))
                   for source in source_paths)
    preserve_build = False
    if icon_path:
        try:
            Path(icon_path).resolve().relative_to(target_build.resolve())
            preserve_build = True
        except ValueError:
            pass
    try:
        if preserve_build or protected(target_build):
            warnings.append(f"构建目录涉及用户选择的 ICO 或附加资源，已保留：{target_build}")
        elif target_build.exists():
            shutil.rmtree(target_build)
            removed.append(str(target_build))
    except Exception as exc:
        warnings.append(f"删除构建目录失败：{target_build} -> {exc}")
    try:
        if (build_root.exists() and build_root.is_dir() and not protected(build_root)
                and not any(build_root.iterdir())):
            build_root.rmdir()
            removed.append(str(build_root))
    except Exception as exc:
        warnings.append(f"删除空 build 目录失败：{build_root} -> {exc}")
    spec_file = workdir / f"{stem}.spec"
    try:
        if protected(spec_file):
            warnings.append(f"SPEC 文件涉及用户选择的资源，已保留：{spec_file}")
        elif spec_file.exists():
            spec_file.unlink()
            removed.append(str(spec_file))
    except Exception as exc:
        warnings.append(f"删除 SPEC 文件失败：{spec_file} -> {exc}")
    return CleanupResult(removed, warnings)


@contextmanager
def resource_build_context(command: Sequence[str], script_path: str,
                           resources: Sequence[ResourceMapping], icon_path: str = "",
                           warning_callback: Optional[Callable[[str], None]] = None) -> Iterator[List[str]]:
    """Stage only directories needing filtering; keep snapshots for the whole build."""
    actual_command = list(command)
    temporary = None
    try:
        for index, resource in enumerate(validate_resources(resources, icon_path, script_path)):
            source = Path(resource.source)
            if not source.is_dir() or not needs_resource_staging(source, script_path):
                continue
            if temporary is None:
                temporary = tempfile.TemporaryDirectory(prefix="python_tool_data_")
            temporary_root = Path(temporary.name).resolve()
            if source == temporary_root or source in temporary_root.parents:
                raise ValueError("资源目录包含工具临时目录，请选择更具体的资源目录：" + str(source))
            staged = temporary_root / ("resource_%d" % index)
            staged.mkdir()
            count = 0
            for file in resource_files(source, script_path):
                destination = staged / file.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)
                count += 1
            previous = f"{source}{os.pathsep}{resource.destination}"
            matches = [position + 1 for position, value in enumerate(actual_command[:-1])
                       if value == "--add-data" and actual_command[position + 1] == previous]
            if not matches:
                raise ValueError("无法匹配资源命令参数：" + str(source))
            for position in matches:
                actual_command[position] = f"{staged}{os.pathsep}{resource.destination}"
            if warning_callback is not None:
                warning_callback(f"[*] 资源过滤：{source} -> {resource.destination}；收录 {count} 个文件，排除构建产物/缓存，使用临时副本。")
        with tkinter_icon_runtime_hook(actual_command, icon_path, warning_callback) as final_command:
            yield final_command
    finally:
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as exc:
                if warning_callback is not None:
                    warning_callback(f"[警告] 资源临时目录清理失败：{exc}")


@contextmanager
def tkinter_icon_runtime_hook(
    command: Sequence[str],
    icon_path: str = "",
    warning_callback: Optional[Callable[[str], None]] = None,
) -> Iterator[List[str]]:
    """在整个构建期间保留 ICO 副本和 Tk 窗口图标 runtime hook。"""
    actual_command = list(command)
    if not icon_path:
        yield actual_command
        return
    hook_dir = tempfile.TemporaryDirectory(prefix="python_tool_icon_")
    try:
        runtime_icon = Path(hook_dir.name) / TK_ICON_RESOURCE_NAME
        shutil.copyfile(icon_path, runtime_icon)
        hook_path = Path(hook_dir.name) / "tk_window_icon.py"
        hook_path.write_text(TK_ICON_RUNTIME_HOOK, encoding="utf-8")
        actual_command[-1:-1] = [
            "--add-data", f"{runtime_icon}{os.pathsep}.",
            "--runtime-hook", str(hook_path),
        ]
        yield actual_command
    finally:
        try:
            hook_dir.cleanup()
        except OSError as exc:
            if warning_callback is not None:
                warning_callback(f"[警告] 图标临时资源清理失败：{exc}")
