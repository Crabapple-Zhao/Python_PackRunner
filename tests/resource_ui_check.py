"""Headful directory/icon editor checks. Never launch PyInstaller."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ui.main_window import UVToolApp
from app.ui.widgets import RoundedButton


def main():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    app = UVToolApp(root)
    try:
        with tempfile.TemporaryDirectory(prefix="资源 UI ") as temp:
            project = Path(temp).resolve() / "项目"
            project.mkdir()
            script = project / "main.py"
            script.write_text("pass", encoding="utf-8")
            ico_dir = project / "doc" / "ico"
            ico_dir.mkdir(parents=True)
            icon = ico_dir / "original.ico"
            icon.write_bytes(b"test icon")
            panel = app.resource_panel
            root.update()
            initial_height = root.winfo_height()
            fixed_panel_size = (panel.winfo_width(), panel.winfo_height())
            fixed_viewport_height = panel.canvas.winfo_height()
            def assert_complete_form():
                assert not hasattr(app, "settings_canvas")
                assert not hasattr(app, "settings_scrollbar")
                widgets = [app.file_entry, app.python_select, app.deps_entry, panel.count_label,
                           panel.icon_selector, panel.refresh_button, panel.directory_button,
                           app.run_btn, app.pack_btn, app.stop_btn, app.no_console_checkbox, app.log_area]
                for widget in widgets:
                    parent = widget.master
                    while parent is not None:
                        assert widget.winfo_rootx() >= parent.winfo_rootx(), str(widget)
                        assert widget.winfo_rooty() >= parent.winfo_rooty(), str(widget)
                        assert widget.winfo_rootx() + widget.winfo_width() <= parent.winfo_rootx() + parent.winfo_width(), str(widget)
                        assert widget.winfo_rooty() + widget.winfo_height() <= parent.winfo_rooty() + parent.winfo_height(), str(widget)
                        if parent is root:
                            break
                        parent = parent.master
                assert panel.winfo_rooty() + panel.winfo_height() < app.action_card.winfo_rooty()
                assert app.log_card.winfo_rooty() + app.log_card.winfo_height() < app.action_card.winfo_rooty()
                assert app.left_form.winfo_rootx() + app.left_form.winfo_width() < app.log_card.winfo_rootx()
                assert panel.icon_selector.winfo_rootx() + panel.icon_selector.winfo_width() < panel.refresh_button.winfo_rootx()
                assert app.log_area.winfo_height() >= app._px(120)

            assert_complete_form()
            assert app.log_area.winfo_height() >= app._px(120)
            assert panel.mappings() == []
            assert panel.empty_hint.winfo_ismapped()
            assert isinstance(panel.directory_button, RoundedButton)
            assert not hasattr(panel, "file_button")
            with patch("app.ui.resource_panel.filedialog.askdirectory", return_value=str(ico_dir)):
                panel.directory_button._click()
            root.update()
            assert len(panel.rows) == 1
            assert panel.rows[0]["variable"].get() == "ico"
            assert panel.selected_icon() == str(icon)
            assert app.icon_path_var.get() == str(icon)
            assert root.winfo_height() == initial_height, "Adding a directory must not resize the main window"
            assert panel.canvas.winfo_height() == fixed_viewport_height
            assert (panel.winfo_width(), panel.winfo_height()) == fixed_panel_size
            assert not panel.empty_hint.winfo_ismapped()
            assert_complete_form()
            assert app.log_area.winfo_height() >= app._px(120), "Resource rows must not compress logs"
            app.file_path_var.set(str(script))
            panel.prepare(str(script))
            assert panel.rows[0]["variable"].get() == "doc/ico", "Rebase auto destinations after entry selection"
            panel.rows[0]["variable"].set("custom/ico")
            panel.prepare(str(script))
            assert panel.rows[0]["variable"].get() == "custom/ico", "Preserve explicit destinations"
            panel.rows[0]["variable"].set("doc/ico")
            panel.rows[0]["variable"].set("../escape")
            assert not panel.validate()
            assert panel.rows[0]["entry"]._border == "#D92D20"
            with patch.object(app, "validate_script", return_value=str(script)), \
                    patch.object(app, "check_uv", return_value=True), \
                    patch.object(app, "start_command") as start, \
                    patch("app.ui.main_window.messagebox.showerror") as error:
                app.pack_exe()
                error.assert_called_once()
                start.assert_not_called()
            panel.rows[0]["variable"].set("doc/ico")

            other_dir = project / "other"
            other_dir.mkdir()
            other_icon = other_dir / "second.ICO"
            other_icon.write_bytes(b"other icon")
            panel.add_paths([str(other_dir)])
            root.update()
            assert panel.rows[1]["frame"].winfo_y() >= panel.rows[0]["frame"].winfo_height()
            assert panel.rows[1]["frame"].winfo_y() + panel.rows[1]["frame"].winfo_height() <= panel.canvas.winfo_height()
            assert (panel.winfo_width(), panel.winfo_height()) == fixed_panel_size
            assert not panel.validate(), "Multiple ICOs require explicit selection"
            assert app.icon_path_var.get() == ""
            panel.choice.set(next(label for label, mode in panel._choice_modes.items() if mode == str(icon)))
            assert panel.validate()
            original_tool_icon = root.iconbitmap()
            with patch.object(app, "validate_script", return_value=str(script)), \
                    patch.object(app, "check_uv", return_value=True), \
                    patch.object(app, "start_command") as start:
                app.pack_exe()
            command, action, target, selected_icon, resources = start.call_args[0]
            assert command.count("--add-data") == 2
            assert "--icon=" + str(icon) in command and selected_icon == str(icon)
            assert len(resources) == 2 and target == str(script)
            assert root.iconbitmap() == original_tool_icon
            extras = [other_dir / ("extra_%d.ico" % number) for number in range(9)]
            for extra in extras:
                extra.write_bytes(b"test")
            panel.refresh()
            root.update()
            panel.icon_selector._open()
            root.update()
            assert panel.icon_selector._popup is not None
            assert panel.icon_selector._popup.winfo_height() <= 8 * 40 + 2
            panel.icon_selector._choose(next(label for label, mode in panel._choice_modes.items()
                                            if mode == str(extras[-1])))
            assert panel.selected_icon() == str(extras[-1])
            panel.choice.set(next(label for label, mode in panel._choice_modes.items() if mode == str(icon)))
            for extra in extras:
                extra.unlink()
            panel.refresh()
            log = Mock()
            with patch.object(app, "safe_log", log):
                app._command_started(action, str(project), selected_icon, command, resources)
            assert any(str(ico_dir) in call[0][0] and "-> doc/ico" in call[0][0] for call in log.call_args_list)

            icon.unlink()
            panel.refresh()
            assert not panel.validate(), "A deleted explicitly selected icon must not silently change"
            icon.write_bytes(b"test icon")
            panel.refresh()
            assert panel.validate()
            panel.choice.set(next(label for label, mode in panel._choice_modes.items() if mode == "none"))
            assert panel.validate() and app.icon_path_var.get() == ""
            with patch.object(app, "validate_script", return_value=str(script)), \
                    patch.object(app, "check_uv", return_value=True), \
                    patch.object(app, "start_command") as start:
                app.pack_exe()
            assert not any(arg.startswith("--icon=") for arg in start.call_args[0][0])
            assert "目标代码" in panel.status.cget("text")

            panel.set_busy(True)
            assert panel.rows[0]["entry"].entry.cget("state") == tk.DISABLED
            panel.rows[0]["remove"]._click()
            panel.add_paths([str(project)])
            assert len(panel.rows) == 2
            panel.set_busy(False)
            panel.rows[1]["remove"]._click()
            root.update()
            assert len(app.resource_mappings) == 1
            assert panel.canvas.winfo_height() == fixed_viewport_height
            assert len(app.resource_mappings) == 1
            assert root.winfo_height() == initial_height
            assert app.log_area.winfo_height() >= app._px(120)
            assert_complete_form()

            for number in range(15):
                folder = project / ("resource_%d" % number)
                folder.mkdir()
                (folder / "config.ini").write_text("test", encoding="utf-8")
                panel.add_paths([str(folder)])
            root.update()
            assert panel.list_frame.winfo_height() > panel.canvas.winfo_height()
            assert panel.canvas.winfo_height() == fixed_viewport_height
            assert (panel.winfo_width(), panel.winfo_height()) == fixed_panel_size
            assert panel.scrollbar.winfo_ismapped()
            assert root.winfo_height() == initial_height
            assert_complete_form()
            original_geometry = root.geometry()
            for width, height in ((1180, 640), (1500, 900)):
                root.geometry("%dx%d" % (width, height))
                root.update()
                assert_complete_form()
            root.geometry(original_geometry)
            root.update()
            for row in list(panel.rows):
                panel.remove(row)
            root.update()
            assert app.resource_mappings == []
            assert panel.empty_hint.winfo_ismapped()
            assert panel.canvas.winfo_height() == fixed_viewport_height
            assert panel.selected_icon() == "" and app.icon_path_var.get() == ""

            root_source = Path(temp) / "根目录提示"
            root_source.mkdir()
            root_script = root_source / "main.py"
            root_script.write_text("pass", encoding="utf-8")
            app.file_path_var.set(str(root_script))
            panel.add_paths([str(root_source)])
            root.update()
            row = panel.rows[0]
            assert row["root_hint"].winfo_ismapped()
            assert row["root_hint"].cget("text") == "包内根目录（.）"
            assert row["variable"].get() == panel.mappings()[0].destination == "."
            nested_script = root_source / "nested" / "main.py"
            nested_script.parent.mkdir()
            nested_script.write_text("pass", encoding="utf-8")
            panel.prepare(str(nested_script))
            root.update()
            assert row["variable"].get() == root_source.name
            assert not row["root_hint"].winfo_ismapped()
            panel.prepare(str(root_script))
            root.update()
            assert row["root_hint"].winfo_ismapped()
            root.focus_force()
            row["root_hint"].event_generate("<Button-1>")
            root.update()
            assert row["entry"].entry.focus_get() is row["entry"].entry
            assert not row["root_hint"].winfo_ismapped()
            assert not row["manual"], "Focusing the root caption must preserve automatic destination rebasing"
            row["entry"].entry.delete(0, tk.END)
            row["entry"].entry.insert(0, "assets")
            app.deps_entry.focus_set()
            root.update()
            assert panel.mappings()[0].destination == "assets"
            assert not row["root_hint"].winfo_ismapped()
            row["variable"].set(".")
            root.update()
            assert row["root_hint"].winfo_ismapped()
            with patch.object(app, "validate_script", return_value=str(root_script)), \
                    patch.object(app, "check_uv", return_value=True), \
                    patch.object(app, "start_command") as start:
                app.pack_exe()
            command = start.call_args[0][0]
            resources = start.call_args[0][4]
            assert resources[0].destination == "."
            assert str(root_source.resolve()) + ";." in command
            assert not any("包内根目录" in argument for argument in command)
            panel.remove(row)
            root.update()
            assert not errors, errors
            print("Directory/icon UI OK: recursive scan, auto/manual/none icons, missing icon, rebasing, compact rows, stable window, validation, busy, scrolling, pack/log")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
