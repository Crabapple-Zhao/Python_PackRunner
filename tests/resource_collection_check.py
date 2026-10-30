"""Check real PyInstaller argument/data expansion without building an EXE.

Run with the existing development PyInstaller environment, not an app dependency.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyInstaller.__main__ import generate_parser
from PyInstaller.building.utils import format_binaries_and_datas
from app.services.pyinstaller_backend import build_pack_command, tkinter_icon_runtime_hook, resource_build_context
from app.services.resources import ResourceMapping, default_resource_destination, scan_directory_icons


def main():
    with tempfile.TemporaryDirectory(prefix="目录 资源验证 ") as temporary:
        project = Path(temporary).resolve() / "项目 空格"
        icon_dir = project / "doc" / "ico"
        icon_dir.mkdir(parents=True)
        script = project / "main.py"
        script.write_text("pass", encoding="utf-8")
        icon = icon_dir / "应用 图标.ico"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "docs/ico/Python_Tool_A2.ico", icon)
        for relative in ("doc/logo/图片.png", "doc/fonts/nested/字体.ttf", "doc/config/settings.json"):
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        directory = project / "doc"
        resources = [ResourceMapping(str(directory), default_resource_destination(str(directory), str(script)))]
        icons = scan_directory_icons(resources)
        assert icons == [str(icon)]
        for no_console in (False, True):
            command = build_pack_command(str(script), "3.8.20", "", no_console, icons[0], resources)
            with tkinter_icon_runtime_hook(command, icons[0]) as actual:
                start = max(index for index, value in enumerate(actual) if value == "pyinstaller")
                parsed = generate_parser().parse_args(actual[start + 1:])
                files = {target.replace("\\", "/"): Path(source) for target, source in format_binaries_and_datas(parsed.datas)}
                assert files["doc/ico/应用 图标.ico"].read_bytes() == icon.read_bytes()
                for relative in ("doc/logo/图片.png", "doc/fonts/nested/字体.ttf", "doc/config/settings.json"):
                    assert relative in files, relative
                assert files["python_tool_window_icon.ico"].read_bytes() == icon.read_bytes()
                assert len(parsed.runtime_hooks) == 1
                temp_dir = Path(parsed.runtime_hooks[0]).parent
            assert not temp_dir.exists()
        # A source file mapping must also preserve its original relative parent.
        command = build_pack_command(str(script), "3.8.20", "", False, "", [
            ResourceMapping(str(icon), default_resource_destination(str(icon), str(script)))])
        start = max(index for index, value in enumerate(command) if value == "pyinstaller")
        parsed = generate_parser().parse_args(command[start + 1:])
        assert any(target.replace("\\", "/") == "doc/ico/应用 图标.ico"
                   for target, source in format_binaries_and_datas(parsed.datas))
        for relative in ("build/main/stale.ico", "dist/old.exe", "__pycache__/main.pyc", ".git/config", "main.spec"):
            artifact = project / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"generated")
        resources = [ResourceMapping(str(project), ".")]
        assert scan_directory_icons(resources, str(script)) == [str(icon)]
        command = build_pack_command(str(script), "3.8.20", "", True, str(icon), resources)
        with resource_build_context(command, str(script), resources, str(icon)) as actual:
            start = max(index for index, value in enumerate(actual) if value == "pyinstaller")
            parsed = generate_parser().parse_args(actual[start + 1:])
            collected = {target.replace("\\", "/"): source for target, source in format_binaries_and_datas(parsed.datas)}
            assert "doc/ico/应用 图标.ico" in collected
            assert "doc/fonts/nested/字体.ttf" in collected
            assert "main.py" in collected
            assert not any(name.startswith(("build/", "dist/", ".git/", "__pycache__/")) or name == "main.spec"
                           for name in collected)
            staged = Path(parsed.datas[0][0]).parent
            hook = Path(parsed.runtime_hooks[0]).parent
        assert not staged.exists() and not hook.exists()
        assert icon.is_file()
        print("Real PyInstaller data collection OK: nested assets, both console modes, project-root filtering, original/runtime ICO paths, snapshot/hook cleanup; NO EXE built")


if __name__ == "__main__":
    main()
