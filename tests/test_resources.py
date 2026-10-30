"""Resource regressions; no EXE builds or target project edits."""
import os
import sys
import tempfile
import unittest
import threading
from functools import partial
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.resources import (ResourceMapping as Mapping, default_resource_destination,
                                    normalize_destination, scan_directory_icons, validate_resources)
from app.services.pyinstaller_backend import (build_pack_command, cleanup_pack_artifacts,
                                               tkinter_icon_runtime_hook, resource_build_context)
from app.core.process_runner import ProcessRunner


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="资源 空格 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "项目"
        self.project.mkdir()
        self.script = self.project / "main.py"
        self.script.write_text("pass", encoding="utf-8")
        self.doc = self.project / "doc"
        (self.doc / "ico").mkdir(parents=True)
        self.file = self.doc / "ico" / "图 标.ico"
        self.file.write_bytes(b"icon")
        (self.doc / "logo").mkdir()
        (self.doc / "logo" / "图.png").write_bytes(b"png")

    def test_default_destinations(self):
        outside = self.root / "外部 字体"
        outside.mkdir()
        file = outside / "font.ttf"
        file.write_bytes(b"font")
        for source, dest in [(self.doc, "doc"), (self.file, "doc/ico"),
                             (outside, outside.name), (file, "."), (self.script, ".")]:
            self.assertEqual(default_resource_destination(str(source), str(self.script)), dest)

    def test_invalid_destinations(self):
        for value in ["", "../x", "a/../../b", "/tmp", "C:/tmp", "C:relative",
                      "\\server\\share", "\\root", "x;data", "NUL", "a."]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_destination(value)
        self.assertEqual(normalize_destination("doc\\ico"), "doc/ico")
        self.assertEqual(normalize_destination("."), ".")

    def test_command_and_nested_directory(self):
        mappings = [Mapping(str(self.doc), "doc"), Mapping(str(self.script), "配置 空格")]
        command = build_pack_command(str(self.script), "3.8.20", "", True, str(self.file), mappings)
        values = [command[i+1] for i, value in enumerate(command) if value == "--add-data"]
        self.assertEqual(values, [str(self.doc) + os.pathsep + "doc",
                                  str(self.script) + os.pathsep + "配置 空格"])
        self.assertEqual(command[-1], str(self.script))
        self.assertIn("--icon=" + str(self.file), command)
        with tkinter_icon_runtime_hook(command, str(self.file)) as actual:
            temporary = Path(actual[-2]).parent
            self.assertTrue((temporary / "python_tool_window_icon.ico").is_file())
            self.assertEqual(actual.count("--add-data"), 3)
        self.assertFalse(temporary.exists())
        self.assertTrue(self.file.is_file())

    def test_duplicate_mapping(self):
        mappings = [Mapping(str(self.doc), "doc"), Mapping(str(self.doc / "."), "doc/.")]
        self.assertEqual(len(validate_resources(mappings)), 1)

    def test_file_collision_and_case(self):
        other = self.root / self.file.name
        other.write_bytes(b"different")
        for dest in ("doc/ico", "DOC/ICO"):
            with self.assertRaisesRegex(ValueError, "资源冲突"):
                validate_resources([Mapping(str(self.doc), "doc"), Mapping(str(other), dest)])

    def test_directory_file_collision_in_both_orders(self):
        file = self.root / "doc"
        file.write_bytes(b"file")
        mappings = [Mapping(str(file), "."), Mapping(str(self.doc), "doc")]
        for items in (mappings, mappings[::-1]):
            with self.assertRaisesRegex(ValueError, "资源冲突"):
                validate_resources(items)

    def test_missing_source_and_reserved_icon(self):
        with self.assertRaises(ValueError):
            validate_resources([Mapping("", ".")])
        with self.assertRaises(OSError):
            validate_resources([Mapping(str(self.root / "missing"), ".")])
        reserved = self.root / "python_tool_window_icon.ico"
        reserved.write_bytes(b"user icon")
        validate_resources([Mapping(str(reserved), ".")])
        with self.assertRaisesRegex(ValueError, "资源冲突"):
            validate_resources([Mapping(str(reserved), ".")], str(self.file))
        validate_resources([Mapping(str(reserved), "doc")], str(self.file))

    def test_failure_cleans_hook_not_sources(self):
        with self.assertRaises(RuntimeError):
            with tkinter_icon_runtime_hook(["pyinstaller", str(self.script)], str(self.file)) as command:
                directory = Path(command[-2]).parent
                raise RuntimeError("build failed")
        self.assertFalse(directory.exists())
        self.assertEqual(self.file.read_bytes(), b"icon")

    def test_cleanup_protects_selected_sources(self):
        build = self.project / "build" / "main"
        build.mkdir(parents=True)
        source = build / "配置.ini"
        source.write_text("config", encoding="utf-8")
        spec = self.script.with_suffix(".spec")
        spec.write_text("user resource", encoding="utf-8")
        result = cleanup_pack_artifacts(str(self.script), resources=[Mapping(str(source), "."), Mapping(str(spec), ".")])
        self.assertTrue(source.is_file())
        self.assertTrue(spec.is_file())
        self.assertEqual(len(result.warnings), 2)

    def test_cleanup_preserves_empty_selected_build_root(self):
        build = self.project / "build"
        build.mkdir()
        cleanup_pack_artifacts(str(self.script), resources=[Mapping(str(build), "build")])
        self.assertTrue(build.is_dir())

    def test_no_resources_unchanged(self):
        command = build_pack_command("demo.py", "3.8.20", "", False)
        self.assertEqual(command[-3:], ["pyinstaller", "--onefile", "demo.py"])

    def test_recursive_icon_scan_and_deduplication(self):
        second = self.doc / "logo" / "second.ICO"
        second.write_bytes(b"second icon")
        icons = scan_directory_icons([Mapping(str(self.doc), "doc"), Mapping(str(self.doc / "ico"), "doc/ico")])
        self.assertEqual(set(icons), {str(self.file), str(second)})

    def test_no_icon_scan_and_file_input_rejected(self):
        self.assertEqual(scan_directory_icons([Mapping(str(self.doc / "logo"), "logo")]), [])
        self.assertEqual(scan_directory_icons([]), [])
        with self.assertRaises(ValueError):
            scan_directory_icons([Mapping("", ".")])
        with self.assertRaisesRegex(ValueError, "目录"):
            scan_directory_icons([Mapping(str(self.file), "doc/ico")])

    def create_artifacts(self):
        for relative in ("build/main/work.bin", "build/main/stale.ico", "dist/old.exe",
                         "dist/old.ico", "__pycache__/main.pyc", ".git/config", ".venv/test.txt", "main.spec"):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"artifact")
        legitimate = self.doc / "build" / "guide.txt"
        legitimate.parent.mkdir()
        legitimate.write_bytes(b"legitimate resource")

    def test_project_root_filtered_then_cleanup_only_generated_outputs(self):
        self.create_artifacts()
        resources = [Mapping(str(self.project), ".")]
        self.assertEqual(scan_directory_icons(resources, str(self.script)), [str(self.file)])
        command = build_pack_command(str(self.script), "3.8.20", "", True, str(self.file), resources)
        with resource_build_context(command, str(self.script), resources, str(self.file)) as actual:
            staged = Path(actual[actual.index("--add-data") + 1].rsplit(os.pathsep, 1)[0])
            hook = Path(actual[-2])
            self.assertEqual((staged / "doc/ico/图 标.ico").read_bytes(), self.file.read_bytes())
            self.assertTrue((staged / "doc/build/guide.txt").is_file())
            for relative in ("build", "dist", ".git", ".venv", "__pycache__", "main.spec"):
                self.assertFalse((staged / relative).exists(), relative)
            (self.project / "build/main/created_after_snapshot.txt").write_bytes(b"new")
            self.assertFalse((staged / "build").exists())
        self.assertFalse(staged.parent.exists())
        self.assertFalse(hook.parent.exists())
        result = cleanup_pack_artifacts(str(self.script), str(self.file), resources)
        self.assertFalse(result.warnings)
        self.assertFalse((self.project / "build").exists())
        self.assertFalse(self.script.with_suffix(".spec").exists())
        self.assertTrue((self.project / "dist/old.exe").is_file())
        self.assertTrue((self.project / "__pycache__/main.pyc").is_file())
        self.assertEqual(self.file.read_bytes(), b"icon")
        self.assertTrue(self.script.is_file())

    def test_explicit_build_resource_still_protected(self):
        source = self.project / "build"
        (source / "main/assets").mkdir(parents=True)
        (source / "main/assets/keep.txt").write_bytes(b"user data")
        cleanup_pack_artifacts(str(self.script), resources=[Mapping(str(source), "assets")])
        self.assertTrue((source / "main/assets/keep.txt").is_file())

    def test_plain_directory_does_not_create_staging(self):
        resources = [Mapping(str(self.doc), "doc")]
        command = build_pack_command(str(self.script), "3.8.20", "", False, "", resources)
        with patch("app.services.pyinstaller_backend.tempfile.TemporaryDirectory") as temp:
            with resource_build_context(command, str(self.script), resources) as actual:
                self.assertEqual(actual, command)
            temp.assert_not_called()

    def test_staging_copy_failure_cleans_temp(self):
        resources = [Mapping(str(self.project), ".")]
        command = build_pack_command(str(self.script), "3.8.20", "", False, "", resources)
        with tempfile.TemporaryDirectory() as temporary:
            prepared = tempfile.TemporaryDirectory(dir=temporary)
            with patch("app.services.pyinstaller_backend.tempfile.TemporaryDirectory", return_value=prepared), \
                    patch("app.services.pyinstaller_backend.shutil.copy2", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    with resource_build_context(command, str(self.script), resources):
                        self.fail("Must not launch build on staging failure")
            self.assertFalse(Path(prepared.name).exists())
        self.assertTrue(self.file.is_file())

    def test_staging_survives_process_and_cleans_after_stop_or_completion(self):
        resources = [Mapping(str(self.project), ".")]
        command = build_pack_command(str(self.script), "3.8.20", "", False, str(self.file), resources)
        for stop in (False, True):
            runner = ProcessRunner()
            ready, done = threading.Event(), threading.Event()
            temporary_paths, results = [], []
            def started(actual):
                staged = Path(actual[actual.index("--add-data") + 1].rsplit(os.pathsep, 1)[0])
                hook = Path(actual[-2])
                temporary_paths.extend([staged.parent, hook.parent])
                actual[:] = [sys.executable, "-u", "-c",
                             "import time;print('ready',flush=True);time.sleep(%s)" % (30 if stop else 0.1)]
            self.assertTrue(runner.start(command, str(self.project), lambda line: ready.set(), started,
                                        lambda result: (results.append(result), done.set()),
                                        partial(resource_build_context, script_path=str(self.script),
                                                resources=resources, icon_path=str(self.file))))
            self.assertTrue(ready.wait(10))
            if stop:
                self.assertTrue(all(path.is_dir() for path in temporary_paths))
                self.assertTrue(runner.stop())
            self.assertTrue(done.wait(10))
            self.assertIsNone(results[0].error)
            self.assertTrue(temporary_paths)
            self.assertTrue(all(not path.exists() for path in temporary_paths))
            self.assertTrue(self.file.is_file())


if __name__ == "__main__":
    unittest.main()
