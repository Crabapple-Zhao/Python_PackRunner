"""Python import analysis and dependency-name normalization."""

import ast
import os
import pkgutil
import re
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple

from ..constants import IMPORT_TO_PACKAGE, STD_LIBS_FALLBACK


@dataclass(frozen=True)
class DependencyAnalysis:
    dependencies: List[str]
    mappings: List[Tuple[str, str]]
    ignored_stdlib: List[str]
    ignored_local: List[str]


def build_stdlib_set() -> Set[str]:
    """尽可能完整地构造标准库顶层模块集合，兼容 Python 3.8+。"""
    modules = set(sys.builtin_module_names) | set(STD_LIBS_FALLBACK)
    stdlib_names = getattr(sys, "stdlib_module_names", None)
    if stdlib_names:
        modules.update(stdlib_names)
    try:
        stdlib_dir = sysconfig.get_path("stdlib")
        if stdlib_dir and os.path.isdir(stdlib_dir):
            for item in pkgutil.iter_modules([stdlib_dir]):
                modules.add(item.name)
    except Exception:
        pass
    return modules


STD_LIBS = build_stdlib_set()


def detect_local_modules(script_path: str) -> Set[str]:
    """识别脚本同目录下的本地 .py 模块和 Python 包。"""
    result = set()
    script_dir = Path(script_path).resolve().parent
    try:
        for child in script_dir.iterdir():
            if child.is_file() and child.suffix.lower() == ".py":
                result.add(child.stem)
            elif child.is_dir() and (child / "__init__.py").exists():
                result.add(child.name)
    except OSError:
        pass
    return result


def normalize_dep_text(text: str) -> List[str]:
    """允许空格、逗号、分号分隔依赖，并去重保序。"""
    raw = [item for item in re.split(r"[\s,;]+", text.strip()) if item]
    seen = set()
    result = []
    for dependency in raw:
        key = dependency.lower()
        if key not in seen:
            seen.add(key)
            result.append(dependency)
    return result


def analyze_imports(file_path: str) -> DependencyAnalysis:
    """分析脚本 import，只返回需要由 uv / pip 安装的第三方依赖。"""
    with open(file_path, "r", encoding="utf-8-sig") as source_file:
        source = source_file.read()
    tree = ast.parse(source, filename=file_path)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if getattr(node, "level", 0) == 0:
                imports.add(node.module.split(".")[0])

    local_modules = detect_local_modules(file_path)
    third_party = []
    ignored_stdlib = []
    ignored_local = []
    for package in sorted(imports, key=str.lower):
        if not package or package.startswith("_"):
            continue
        if package in STD_LIBS:
            ignored_stdlib.append(package)
        elif package in local_modules:
            ignored_local.append(package)
        else:
            third_party.append(package)

    dependencies = []
    mappings = []
    seen = set()
    for package in third_party:
        dependency = IMPORT_TO_PACKAGE.get(package, package)
        if dependency != package:
            mappings.append((package, dependency))
        key = dependency.lower()
        if key not in seen:
            seen.add(key)
            dependencies.append(dependency)
    return DependencyAnalysis(dependencies, mappings, ignored_stdlib, ignored_local)
