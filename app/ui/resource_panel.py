"""Directory-based resources and one explicit icon policy, in a compact card."""
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from ..services.resources import (ResourceMapping, default_resource_destination,
                                   normalize_destination, scan_directory_icons, validate_resources)
from .widgets import RoundedEntry, RoundedFrame, RoundedScrollbar, RoundedSelect


class ResourcePanel(RoundedFrame):
    def __init__(self, parent, colors, scale, font, make_button, script_path,
                 on_change, on_icon_change):
        super().__init__(parent, fill=colors["card"], background=colors["window"],
                         border=colors["border_soft"], radius=scale(10), height=scale(280))
        self.colors, self.scale, self.font = colors, scale, font
        self.make_button, self.script_path = make_button, script_path
        self.on_change, self.on_icon_change = on_change, on_icon_change
        self.rows, self.busy = [], False
        self.validation_job = self.layout_job = None
        self.icons, self.icon_mode, self.scan_error, self.error_text = [], "auto", "", ""
        self._updating_choice = False
        self._width = 0
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)
        self.header = tk.Frame(self.content, bg=colors["card"])
        self.header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        self.header.grid_columnconfigure(2, weight=1)
        self.count_label = tk.Label(self.header, text="资源与图标 (0)", bg=colors["card"],
                                    fg=colors["text"], font=(font[0], font[1], "bold"))
        self.count_label.grid(row=0, column=0, sticky="w", padx=(3, 8))
        tk.Label(self.header, text="程序图标", bg=colors["card"],
                 fg=colors["muted"], font=font).grid(row=0, column=1, sticky="w", padx=(10, 6))
        self.refresh_button = make_button(self.header, "重新扫描", self.refresh, width=85, height=30)
        self.refresh_button.grid(row=0, column=3, padx=(8, 0))
        self.directory_button = make_button(self.header, "＋ 添加目录", self.add_directory,
                                            kind="secondary", width=110, height=30)
        self.directory_button.grid(row=0, column=4, padx=(6, 0))
        self.choice = tk.StringVar(value="自动（未发现 ICO）")
        self.icon_selector = RoundedSelect(
            self.header, self.choice, [self.choice.get()], width=scale(200), height=scale(28),
            radius=scale(7), background="#F7F9FC", parent_background=colors["card"],
            border=colors["border"], focus_border=colors["primary"],
            foreground=colors["text"], muted=colors["muted"], font=font)
        self.icon_selector.grid(row=0, column=2, sticky="ew")
        self._choice_modes = {self.choice.get(): "auto"}
        self.choice.trace_add("write", self._choice_changed)

        self.body = tk.Frame(self.content, bg=colors["card"])
        self.body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(4, 6))
        self.headings = tk.Frame(self.body, bg=colors["card"])
        self.headings.pack(fill=tk.X)
        self.headings.grid_columnconfigure(0, weight=1)
        tk.Label(self.headings, text="资源目录（只读，可选择复制）", bg=colors["card"],
                 fg=colors["muted"], font=font).grid(row=0, column=0, sticky="w")
        tk.Label(self.headings, text="包内目标目录 · 直接修改", width=27,
                 bg=colors["card"], fg=colors["muted"], font=font).grid(row=0, column=1, padx=(8, 36))
        viewport = tk.Frame(self.body, bg=colors["card"])
        viewport.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self.canvas = tk.Canvas(viewport, height=scale(32), bg=colors["card"], highlightthickness=0)
        self.scrollbar = RoundedScrollbar(
            viewport, command=self.canvas.yview, width=scale(8), background=colors["card"],
            track="#F3F6FA", thumb="#C9D2DE", hover_thumb="#98A2B3", min_thumb=scale(20))
        self.scrollbar.configure(height=scale(32))
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.list_frame = tk.Frame(self.canvas, bg=colors["card"])
        self.list_window = self.canvas.create_window(0, 0, anchor="nw", window=self.list_frame)
        self.empty_hint = tk.Label(self.list_frame, text="还没有资源目录\n点击右上角“添加目录”，完整收录所需资源",
                                   bg=colors["card"], fg=colors["muted"], font=font, justify=tk.CENTER)
        self.canvas.bind("<Configure>", self._canvas_configured)
        self.list_frame.bind("<Configure>", self._scroll_region)
        self.canvas.bind("<MouseWheel>", self._scroll)
        self.list_frame.bind("<MouseWheel>", self._scroll)
        self.status = tk.Label(self.content, anchor="w", justify=tk.LEFT, height=1,
                               bg=colors["card"], fg=colors["muted"], font=font)
        self.status.grid(row=3, column=0, sticky="ew", padx=10, pady=(1, 4))
        self.bind("<Configure>", self._configured, add="+")
        self.bind("<Destroy>", self._destroyed, add="+")
        self.refresh()

    def mappings(self):
        return [ResourceMapping(row["source"], row["variable"].get()) for row in self.rows]

    def _configured(self, event):
        if event.width != self._width:
            self._width = event.width
            self._schedule_layout()

    def _schedule_layout(self):
        if self.layout_job:
            self.after_cancel(self.layout_job)
        self.layout_job = self.after_idle(self._layout)

    def _layout(self):
        self.layout_job = None
        if self.rows:
            self.empty_hint.pack_forget()
        else:
            self.empty_hint.pack(fill=tk.X, pady=self.scale(28))
        self.count_label.configure(text="资源与图标 (%d)" % len(self.rows))
        self._scroll_region()

    def _canvas_configured(self, event):
        self.canvas.itemconfigure(self.list_window, width=event.width)
        self._scroll_region()

    def _scroll_region(self, event=None):
        if self.rows and self.list_frame.winfo_reqheight() > self.canvas.winfo_height():
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)
        else:
            self.scrollbar.pack_forget()
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(),
                                            max(self.canvas.winfo_height(), self.list_frame.winfo_reqheight())))
        if self.list_frame.winfo_reqheight() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)

    def add_directory(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self.winfo_toplevel(), title="添加资源目录（递归收录文件）")
            if path:
                self.add_paths([path])

    def add_paths(self, paths):
        if self.busy:
            return
        script = self.script_path()
        if script and not Path(script).exists():
            script = ""
        for path in paths:
            source = str(Path(path).resolve())
            if not Path(source).is_dir():
                self.status.configure(text="请选择资源目录，不再单独添加文件。", fg="#D92D20")
                self._schedule_layout()
                continue
            if any(os.path.normcase(row["source"]) == os.path.normcase(source) for row in self.rows):
                continue
            dest = default_resource_destination(source, script) if script else Path(source).name
            frame = tk.Frame(self.list_frame, bg=self.colors["card"])
            frame.pack(fill=tk.X, pady=1)
            frame.grid_columnconfigure(0, weight=1)
            source_entry = tk.Entry(frame, relief=tk.FLAT, readonlybackground=self.colors["card"],
                                    fg=self.colors["text"], font=self.font)
            source_entry.insert(0, source)
            source_entry.configure(state="readonly")
            source_entry.grid(row=0, column=0, sticky="ew")
            source_entry.bind("<MouseWheel>", self._scroll)
            frame.bind("<MouseWheel>", self._scroll)
            variable = tk.StringVar(value=dest)
            entry = RoundedEntry(frame, variable, height=self.scale(29), radius=self.scale(7),
                                 background="#F7F9FC", parent_background=self.colors["card"],
                                 border=self.colors["border"], focus_border=self.colors["primary"],
                                 foreground=self.colors["text"], font=self.font, width=self.scale(205))
            entry.grid(row=0, column=1, padx=(8, 5))
            entry.bind("<MouseWheel>", self._scroll)
            row = {"source": source, "variable": variable, "frame": frame, "entry": entry, "manual": False}
            row["root_hint"] = tk.Label(
                entry.entry, text="包内根目录（.）", anchor="w", padx=0,
                bg=entry.entry.cget("bg"), fg=self.colors["text"], font=self.font, cursor="xterm")
            row["root_hint"].bind("<Button-1>", lambda event, row=row: self._edit_root_destination(row))
            entry.bind("<FocusIn>", lambda event, row=row: self._refresh_destination_hint(row))
            entry.bind("<FocusOut>", lambda event, row=row: self._refresh_destination_hint(row))
            row["remove"] = self.make_button(frame, "×", lambda row=row: self.remove(row), width=28, height=28)
            row["remove"].grid(row=0, column=2)
            row["trace"] = variable.trace_add("write", lambda *args, row=row: self._edited(row))
            self.rows.append(row)
        if paths:
            self.refresh()
            self._changed()

    def _edited(self, row):
        row["manual"] = True
        self._changed()

    def _refresh_destination_hint(self, row):
        # Keep the real path in the variable; the caption is display-only.
        entry = row["entry"].entry
        try:
            root_destination = normalize_destination(row["variable"].get()) == "."
        except ValueError:
            root_destination = False
        if root_destination and entry.focus_get() is not entry:
            row["root_hint"].place(x=0, y=0, relwidth=1, relheight=1)
        else:
            row["root_hint"].place_forget()

    def _edit_root_destination(self, row):
        if not self.busy:
            row["root_hint"].place_forget()
            row["entry"].focus_set()
            row["entry"].entry.selection_range(0, tk.END)
            row["entry"].entry.icursor(tk.END)
        return "break"

    def remove(self, row):
        if self.busy:
            return
        if self.icon_mode not in ("auto", "none") and Path(row["source"]) in Path(self.icon_mode).parents:
            self.icon_mode = "auto"
        row["variable"].trace_remove("write", row["trace"])
        row["frame"].destroy()
        self.rows.remove(row)
        self.refresh()
        self._changed()

    def _scroll(self, event):
        if self.list_frame.winfo_reqheight() <= self.canvas.winfo_height():
            return None  # Only the resource list scrolls, and only when necessary.
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _changed(self):
        self.on_change(self.mappings())
        for row in self.rows:
            try:
                normalize_destination(row["variable"].get())
                invalid = False
            except ValueError:
                invalid = True
            row["entry"].set_invalid(invalid)
            self._refresh_destination_hint(row)
        if self.validation_job:
            self.after_cancel(self.validation_job)
        self.validation_job = self.after(250, self.validate)

    def _auto_label(self):
        if len(self.icons) == 1:
            return "自动：" + Path(self.icons[0]).name
        return "自动（发现 %d 个 ICO，请选择）" % len(self.icons) if self.icons else "自动（未发现 ICO）"

    def refresh(self):
        if self.busy:
            return
        try:
            self.icons = scan_directory_icons(self.mappings(), self.script_path())
            self.scan_error = ""
        except (ValueError, OSError) as error:
            self.scan_error = str(error)
        modes = {self._auto_label(): "auto", "不设置 EXE 图标（窗口由目标程序决定）": "none"}
        script = self.script_path()
        base = Path(script).resolve() if script and Path(script).is_dir() else Path(script).resolve().parent if script else None
        for number, icon in enumerate(self.icons, 1):
            try:
                label = Path(icon).relative_to(base).as_posix() if base else icon
            except ValueError:
                label = icon
            if len(label) > 62:
                label = "…" + label[-61:]
            modes["%d. %s" % (number, label)] = icon
        if self.icon_mode not in modes.values():
            modes["已失效：" + Path(self.icon_mode).name] = self.icon_mode
        self._choice_modes = modes
        self._updating_choice = True
        try:
            self.icon_selector.set_values(list(modes))
            self.choice.set(next(label for label, mode in modes.items() if mode == self.icon_mode))
        finally:
            self._updating_choice = False
        self._publish_icon()
        self.validate()

    def _choice_changed(self, *args):
        if not self._updating_choice:
            self.icon_mode = self._choice_modes[self.choice.get()]
            self._publish_icon()
            self.validate()

    def selected_icon(self):
        if self.scan_error:
            raise ValueError(self.scan_error)
        if self.icon_mode == "none":
            return ""
        if self.icon_mode == "auto":
            if len(self.icons) > 1:
                raise ValueError("发现多个 ICO，请在“程序图标”中选择一个，或明确选择不设置 EXE 图标。")
            return self.icons[0] if self.icons else ""
        if self.icon_mode not in self.icons or not Path(self.icon_mode).is_file():
            raise ValueError("所选程序图标已失效，请重新选择或扫描资源目录。")
        return self.icon_mode

    def _publish_icon(self):
        try:
            path = self.selected_icon()
        except ValueError:
            path = ""
        self.on_icon_change(path)

    def prepare(self, script):
        # Adding directories before choosing an entry script must not freeze the wrong destination.
        for row in self.rows:
            if not row["manual"]:
                dest = default_resource_destination(row["source"], script)
                row["variable"].trace_remove("write", row["trace"])
                row["variable"].set(dest)
                row["trace"] = row["variable"].trace_add("write", lambda *args, row=row: self._edited(row))
                self._refresh_destination_hint(row)
        self.on_change(self.mappings())
        self.refresh()
        if not self.validate():
            raise ValueError(self.error_text)
        return self.selected_icon()

    def validate(self):
        if self.validation_job:
            self.after_cancel(self.validation_job)
            self.validation_job = None
        try:
            icon = self.selected_icon()
            validate_resources(self.mappings(), icon, self.script_path())
            if self.icon_mode == "none":
                text = "不设置 EXE 文件图标；目标代码仍可能自行设置窗口和任务栏图标。"
            elif icon:
                text = "图标用于 EXE 文件和默认 Tk 窗口；目录按目标路径收录，保留内部层级。"
            else:
                text = "未发现 ICO，使用默认 EXE 图标；可添加包含资源及 ICO 的目录。"
            self.error_text = ""
            self.status.configure(text=text, fg=self.colors["muted"])
            valid = True
        except (ValueError, OSError) as error:
            self.error_text = str(error)
            self.status.configure(text=self.error_text.replace("\n", " · ")[:220], fg="#D92D20")
            valid = False
        self._schedule_layout()
        return valid

    def set_busy(self, busy):
        self.busy = busy
        for button in [self.refresh_button, self.directory_button] + [row["remove"] for row in self.rows]:
            button.set_state(tk.DISABLED if busy else tk.NORMAL)
        self.icon_selector.set_state(tk.DISABLED if busy else tk.NORMAL)
        for row in self.rows:
            row["entry"].entry.configure(state=tk.DISABLED if busy else tk.NORMAL)

    def _destroyed(self, event):
        if event.widget is self:
            for job in (self.validation_job, self.layout_job):
                if job:
                    self.after_cancel(job)
            self.validation_job = self.layout_job = None
