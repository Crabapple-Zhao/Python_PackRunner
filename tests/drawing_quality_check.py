"""Headful graphics/state/resize checks; standard library only, no EXE build."""
import base64
import sys
import tempfile
import tkinter as tk
from tkinter import font as tkfont, ttk
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ui._raster_masks import MASKS
from app.ui.drawing import draw_icon, draw_rounded_rectangle
from app.ui.main_window import UVToolApp
from app.ui.widgets import RoundedButton


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def main():
    for (kind, size), data in MASKS.items():
        raw = zlib.decompress(base64.b64decode(data))
        assert len(raw) == size*size, (kind, size)
        if kind != "corner":
            assert any(0 < alpha < 255 for alpha in raw), (kind, size)
    for scale in (4/3, 5/3, 2, 8/3):
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            root.tk.call("tk", "scaling", scale)
            app = UVToolApp(root)
            root.update()
            buttons = [widget for widget in descendants(root) if isinstance(widget, RoundedButton)]
            for button in buttons:
                previous_state = button._state
                button.set_state(tk.NORMAL)
                button._enter()
                button._leave()
                button.set_state(tk.DISABLED)
                button.set_state(previous_state)
                for tag in ("button_icon", "label"):
                    box = button.bbox(tag)
                    if box:
                        assert box[0] >= 0 and box[2] <= button.winfo_width(), (button._text, box)
            for entry in (app.file_entry, app.deps_entry):
                entry.focus_set()
                entry.set_invalid(True)
                root.update()
                assert entry.find_withtag("entry_surface")
                entry.set_invalid(False)
            for kind in ("ready", "running", "success", "warning", "error"):
                app._set_status(kind, kind)
                root.update()
                assert app.status_dot.type(app._status_dot_id) == "image"
            for state in (False, True):
                app.no_console_var.set(state)
                root.update()
            app.python_select._open()
            root.update()
            app.python_select._choose("3.8.20")
            for number in range(100):
                app.log("scroll %d" % number)
            root.update()
            app.log_scrollbar._enter()
            app.log_scrollbar._leave()
            app.log_area.yview_moveto(1)
            root.update()
            assert app.log_scrollbar.find_withtag("scroll_thumb")
            # Exercise every graphic, including less frequently used dialog icons.
            canvas = tk.Canvas(root, width=64, height=64)
            for kind in sorted({key[0] for key in MASKS} - {"corner"}):
                draw_icon(canvas, kind, 32, 32, 24, "#0878F9")
                assert canvas.type(canvas.find_withtag("icon")[0]) == "image"
            for width in (1, 2, 3, 8, 20, 48):
                draw_rounded_rectangle(canvas, 0, 0, width, 10, 5, "#FFFFFF", "#0878F9")
            canvas.destroy()
            # Repeated animation/redraws must reuse images instead of leaking one per frame.
            app.progress.configure(mode="indeterminate")
            root.update()
            image_count = len(root.tk.call("image", "names"))
            for number in range(200):
                app.progress._phase = number % 101
                app.progress._redraw()
                app.pack_btn._redraw()
                app.file_entry._redraw()
            assert len(root.tk.call("image", "names")) <= image_count+8
            for width,height in ((1180,640),(1500,900)):
                root.geometry("%dx%d" % (width,height))
                root.update()
                assert app.log_area.winfo_height() > 120
                assert app.no_console_checkbox.winfo_rootx()+app.no_console_checkbox.winfo_width() < app.status_surface.winfo_rootx()
            with tempfile.TemporaryDirectory(prefix="graphics dialog ") as temporary:
                directory = Path(temporary)
                files = [directory / ("script_%02d.py" % number) for number in range(30)]
                for file in files:
                    file.write_text("pass", encoding="utf-8")

                def check_dialog():
                    dialog = next(widget for widget in root.winfo_children() if isinstance(widget, tk.Toplevel))
                    try:
                        tree = next(widget for widget in descendants(dialog) if isinstance(widget, ttk.Treeview))
                        metrics = tkfont.Font(root=dialog, font=(app.ui_font_family,9))
                        assert int(ttk.Style(root).lookup("Modern.Treeview","rowheight")) >= metrics.metrics("linespace")+4
                        assert tree.column("modified","width") >= metrics.measure("2000-00-00 00:00")+16
                        assert dialog.winfo_height() <= dialog.winfo_screenheight()-80
                    finally:
                        dialog.destroy()

                root.after(50, check_dialog)
                assert app._choose_script_dialog(directory, files) is None
            assert not errors, errors
            print("Graphics/state/resize/cache OK at Tk scaling", scale)
        finally:
            root.destroy()
    print("All %d pre-rendered masks checked; no runtime imaging dependency" % len(MASKS))


if __name__ == "__main__":
    main()
