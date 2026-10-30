"""Validate explicit PyInstaller data mappings without changing user files."""

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Sequence

from ..constants import TK_ICON_RESOURCE_NAME


@dataclass(frozen=True)
class ResourceMapping:
    source: str
    destination: str


CACHE_DIRECTORIES = {"__pycache__", ".git", ".hg", ".svn", ".venv", ".pytest_cache", ".mypy_cache"}


def resource_is_ignored(source: Path, path: Path, script_path: str = "") -> bool:
    """Filter generated descendants, never reinterpret an explicitly selected source."""
    if path == source:
        return False
    relative = path.relative_to(source)
    if any(part.casefold() in CACHE_DIRECTORIES for part in relative.parts):
        return True
    if path.suffix.lower() in (".pyc", ".pyo"):
        return True
    if script_path:
        script = Path(script_path).resolve()
        base = script if script.is_dir() else script.parent
        for generated in (base / "build", base / "dist"):
            if source in generated.parents and (path == generated or generated in path.parents):
                return True
        if not script.is_dir() and path == base / (script.stem + ".spec"):
            return True
    return False


def resource_files(source: Path, script_path: str = ""):
    """Yield filtered directory contents, rejecting links instead of following them."""
    def walk_error(error):
        raise error
    for root, folders, names in os.walk(str(source), onerror=walk_error, followlinks=False):
        folders[:] = [name for name in folders if not resource_is_ignored(source, Path(root) / name, script_path)]
        names = [name for name in names if not resource_is_ignored(source, Path(root) / name, script_path)]
        for name in folders + names:
            child = Path(root) / name
            if child.is_symlink() or child.resolve() != child.absolute():
                raise ValueError("暂不支持链接或联接目录资源：" + str(child))
        for name in names:
            child = Path(root) / name
            if not child.is_file():
                raise ValueError("资源不是普通文件：" + str(child))
            yield child


def needs_resource_staging(source: Path, script_path: str) -> bool:
    script = Path(script_path).resolve()
    base = script if script.is_dir() else script.parent
    if source == base or source in base.parents:
        return True  # Snapshot before PyInstaller creates new artifacts in this directory.
    def walk_error(error):
        raise error
    for root, folders, names in os.walk(str(source), onerror=walk_error, followlinks=False):
        if any(resource_is_ignored(source, Path(root) / name, script_path) for name in folders + names):
            return True
    return False


def default_resource_destination(source: str, script_path: str) -> str:
    path = Path(source).resolve()
    script = Path(script_path).resolve()
    base = script if script.is_dir() else script.parent
    try:
        relative = path.relative_to(base)
    except ValueError:
        return path.name if path.is_dir() else "."
    return relative.as_posix() if path.is_dir() else relative.parent.as_posix()


def normalize_destination(value: str) -> str:
    value = value.strip().replace("\\", "/")
    windows = PureWindowsPath(value)
    if not value or windows.drive or windows.root or value.startswith("/"):
        raise ValueError("包内目标目录必须是相对路径，根目录请填写 .")
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise ValueError("包内目标目录不能包含向上路径 ..")
    for part in parts:
        if (any(char in part for char in '<>:"|?*;') or
                part.endswith((".", " ")) or
                (os.path.isreserved(part) if hasattr(os.path, "isreserved")
                 else PureWindowsPath(part).is_reserved())):
            raise ValueError("包内目标目录含有 Windows 不支持的名称：" + part)
    return PurePosixPath(value).as_posix()


def scan_directory_icons(resources: Sequence[ResourceMapping], script_path: str = "") -> List[str]:
    """Scan only explicit resource directories; never infer a project root."""
    icons = set()
    for item in resources:
        if not item.source.strip():
            raise ValueError("资源目录不能为空")
        directory = Path(item.source).resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("请选择资源目录，而不是单个文件：" + str(directory))
        icons.update(str(path) for path in resource_files(directory, script_path)
                     if path.suffix.lower() == ".ico")
    return sorted(icons, key=str.casefold)


def validate_resources(resources: Sequence[ResourceMapping], icon_path: str = "",
                       script_path: str = "") -> List[ResourceMapping]:
    """Resolve/deduplicate mappings and reject case-insensitive file collisions.

    Reject links instead of silently skipping directories or traversing cycles.
    Check file-vs-directory collisions as well as identical output filenames.
    """
    result, mappings, files, directories = [], set(), {}, set()
    if icon_path:
        files[TK_ICON_RESOURCE_NAME.casefold()] = "窗口图标保留资源"

    def directory(name):
        key = name.casefold()
        if key in files:
            raise ValueError("资源冲突（文件与目录）：" + name)
        directories.add(key)

    def add_file(name, source):
        key = name.casefold()
        if key in files or key in directories:
            raise ValueError("资源冲突：%s\n%s\n%s" % (name, files.get(key, "包内目录"), source))
        for parent in PurePosixPath(name).parents:
            if str(parent) != ".":
                directory(str(parent))
        files[key] = str(source)

    for item in resources:
        if not item.source.strip():
            raise ValueError("资源源路径不能为空")
        path = Path(item.source).expanduser().absolute()
        if path.is_symlink():
            raise ValueError("暂不支持符号链接资源：" + str(path))
        path = path.resolve(strict=True)
        if not path.is_file() and not path.is_dir():
            raise ValueError("资源不是普通文件或目录：" + str(path))
        if ";" in str(path):
            raise ValueError("资源路径不能包含 PyInstaller 分隔符 ;：" + str(path))
        dest = normalize_destination(item.destination)
        identity = (os.path.normcase(str(path)), dest.casefold())
        if identity in mappings:
            continue
        mappings.add(identity)
        if path.is_file():
            add_file(str(PurePosixPath(dest) / path.name), path)
        else:
            if dest != ".":
                for parent in [PurePosixPath(dest)] + list(PurePosixPath(dest).parents):
                    if str(parent) != ".":
                        directory(str(parent))
            def walk_error(error):
                raise error
            for root, folders, names in os.walk(str(path), onerror=walk_error, followlinks=False):
                folders[:] = [name for name in folders if not resource_is_ignored(path, Path(root) / name, script_path)]
                names = [name for name in names if not resource_is_ignored(path, Path(root) / name, script_path)]
                for name in folders + names:
                    child = Path(root) / name
                    # Resolve reparse/junction targets too; no external traversal.
                    if child.is_symlink() or child.resolve() != child.absolute():
                        raise ValueError("暂不支持链接或联接目录资源：" + str(child))
                    relative = child.relative_to(path).as_posix()
                    target = str(PurePosixPath(dest) / relative)
                    if name in folders:
                        directory(target)
                    elif child.is_file():
                        add_file(target, child)
                    else:
                        raise ValueError("资源不是普通文件：" + str(child))
        result.append(ResourceMapping(str(path), dest))
    return result
