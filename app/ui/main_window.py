"""Tkinter user interface and application workflow orchestration."""

import os
import sys
import time
import tkinter as tk
from functools import partial
from math import ceil
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from ..constants import APP_VERSION, DEFAULT_PYTHON
from ..core.dependency_analyzer import analyze_imports
from ..core.process_runner import ProcessResult, ProcessRunner
from ..core.script_locator import (
    find_preferred_script,
    list_python_scripts,
    normalize_path_text,
)
from ..services.pyinstaller_backend import (
    build_pack_command,
    cleanup_pack_artifacts,
    resource_build_context,
    tkinter_icon_runtime_hook,
)
from ..services.uv_manager import build_run_command, is_uv_available
from ..services.resources import validate_resources
from ..utils.command import format_command
from .assets import APP_ICON_PNG
from .drawing import draw_icon
from .resource_panel import ResourcePanel
from .widgets import (
    RoundedButton,
    RoundedEntry,
    RoundedFrame,
    RoundedProgressBar,
    RoundedScrollbar,
    RoundedSelect,
    draw_rounded_rectangle,
)


COLORS = {
    "window": "#F3F6FA",
    "card": "#FFFFFF",
    "text": "#10203D",
    "muted": "#667085",
    "border": "#D7E0EB",
    "border_soft": "#E5EBF2",
    "primary": "#0878F9",
    "primary_hover": "#0068DE",
    "primary_soft": "#E8F2FF",
    "option_panel": "#F7FAFE",
    "success": "#2DA44E",
    "danger": "#E5484D",
    "danger_hover": "#CF3F44",
    "warning": "#D97706",
    "disabled": "#A8AFBA",
    "disabled_bg": "#ECEFF3",
    "log": "#18181B",
    "log_text": "#D7DAE0",
}

PYTHON_VERSIONS = ["3.8.20", "3.9", "3.10", "3.11", "3.12", "3.13"]
FORM_ACTION_WIDTH = 112
FORM_CONTROL_HEIGHT = 36
ICON_SIZES = {
    "section": {"normal": 34, "compact": 30},
    "field": {"normal": 22, "compact": 18},
}


class UVToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python运行打包工具")
        self.root.configure(bg=COLORS["window"])
        scaling = max(
            1.0,
            float(self.root.tk.call("tk", "scaling")) / (96.0 / 72.0),
        )
        self.ui_scale = scaling
        self.geometry_scale = 1.0 + (scaling - 1.0) * 0.3
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        # Keep a compact desktop footprint while respecting the available
        # screen area on smaller displays.
        window_width = min(round(1200 * scaling), max(1180, screen_width - 80))
        window_height = min(round(720 * scaling), max(640, screen_height - 80))
        self.window_width = window_width
        self.window_height = window_height
        self.compact_ui = True
        self.form_action_width = 100 if self.compact_ui else FORM_ACTION_WIDTH
        self.form_control_height = 30 if self.compact_ui else FORM_CONTROL_HEIGHT
        self.root.minsize(
            min(round(1180 * self.geometry_scale), window_width),
            min(round(640 * self.geometry_scale), window_height),
        )
        center_window(self.root, window_width, window_height)

        self.file_path_var = tk.StringVar()
        self.icon_path_var = tk.StringVar()
        self.deps_var = tk.StringVar()
        self.python_var = tk.StringVar(value=DEFAULT_PYTHON)
        self.no_console_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="就绪")
        self.process_runner = ProcessRunner()
        self.resource_mappings = []
        self._selected_script_path = ""
        self._stop_requested = False

        self._configure_styles()
        self.app_icon_image = tk.PhotoImage(data=APP_ICON_PNG)
        self.header_icon_image = self.app_icon_image
        self.root.iconphoto(True, self.app_icon_image)
        self._build_ui()
        tool_window_icon = self._resolve_tool_window_icon()
        if tool_window_icon:
            self._apply_tool_window_icon(tool_window_icon)

    # ---------------- UI ----------------

    def _configure_styles(self):
        """Configure a dependency-free modern ttk theme for Windows 10/11."""
        families = {name.lower(): name for name in tkfont.families(self.root)}
        fallback_family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.ui_font_family = families.get("microsoft yahei ui", fallback_family)
        self.mono_font_family = families.get(
            "cascadia mono", families.get("consolas", "Courier New")
        )
        # Fit both the native DPI-scaled text and the icon inside form buttons.
        metrics = tkfont.Font(root=self.root, font=(self.ui_font_family, 9))
        icon_size = min(self._px(self.form_control_height)-10, round(metrics.metrics("linespace")*0.95))
        minimum_width = metrics.measure("重新识别") + icon_size + max(5, round(icon_size*0.3)) + 12
        self.form_action_width = max(self.form_action_width, ceil(minimum_width/self.geometry_scale))

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor=COLORS["border_soft"],
            background=COLORS["primary"],
            bordercolor=COLORS["window"],
            lightcolor=COLORS["primary"],
            darkcolor=COLORS["primary"],
            thickness=3,
        )
        style.configure(
            "Modern.Treeview",
            background=COLORS["card"],
            fieldbackground=COLORS["card"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            rowheight=max(self._px(30), metrics.metrics("linespace")+self._px(8)),
            font=(self.ui_font_family, 9),
        )
        style.configure(
            "Modern.Treeview.Heading",
            background="#F2F4F7",
            foreground=COLORS["muted"],
            relief="flat",
            padding=(8, 7),
            font=(self.ui_font_family, 9, "bold"),
        )
        style.map(
            "Modern.Treeview",
            background=[("selected", COLORS["primary_soft"])],
            foreground=[("selected", COLORS["text"])],
        )

    def _px(self, value):
        return max(1, round(value * self.geometry_scale))

    def _layout_px(self, value):
        """Scale fixed vertical layout more gently so logs retain useful space."""
        layout_scale = 1.0 + (self.ui_scale - 1.0) * 0.2
        return max(1, round(value * layout_scale))

    def _make_button(
        self, parent, text, command, kind="neutral", width=110, height=38,
        icon_kind=None,
    ):
        palettes = {
            "primary": (
                COLORS["primary"], "#FFFFFF", COLORS["primary_hover"],
                COLORS["primary"], True,
            ),
            "secondary": (
                COLORS["card"], COLORS["primary"], COLORS["primary_soft"],
                COLORS["primary"], True,
            ),
            "danger": (
                COLORS["danger"], "#FFFFFF", COLORS["danger_hover"],
                COLORS["danger"], True,
            ),
            "neutral": (
                "#F7F9FC", "#344054", "#E9EEF5", "#C9D2DE", False,
            ),
        }
        background, foreground, hover, border, bold = palettes[kind]
        return RoundedButton(
            parent,
            text=text,
            command=command,
            width=self._px(width),
            height=self._px(height),
            radius=self._px(8),
            background=background,
            foreground=foreground,
            hover_background=hover,
            parent_background=parent.cget("bg"),
            border=border,
            font=(self.ui_font_family, 9, "bold" if bold else "normal"),
            disabled_background=COLORS["disabled_bg"],
            disabled_foreground=COLORS["disabled"],
            icon_kind=icon_kind,
        )

    def _make_form_button(
        self, parent, text, command, kind="neutral", icon_kind=None
    ):
        """Create a consistently sized button centered in a form row."""
        return self._make_button(
            parent,
            text,
            command,
            kind=kind,
            width=self.form_action_width,
            height=self.form_control_height,
            icon_kind=icon_kind,
        )

    def _create_card(self, parent, row, title, subtitle, height, icon_kind):
        compact = self.compact_ui
        card = RoundedFrame(
            parent,
            fill=COLORS["card"],
            background=COLORS["window"],
            border=COLORS["border_soft"],
            radius=self._px(10 if self.compact_ui else 12),
            height=self._layout_px(height),
        )
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 6 if compact else 10))
        container = card.content
        container.grid_columnconfigure(0, weight=1)

        header = tk.Frame(container, bg=COLORS["card"])
        header.grid(
            row=0, column=0, sticky="ew",
            padx=12 if compact else 16,
            pady=(4, 2) if compact else (8, 4),
        )
        header.grid_columnconfigure(1, weight=1)
        section_icon = self._section_icon(header, icon_kind)
        if section_icon is not None:
            section_icon.grid(
                row=0,
                column=0,
                rowspan=2 if subtitle else 1,
                sticky="w",
                padx=(0, 6 if compact else 10),
            )
        tk.Label(
            header,
            text=title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(self.ui_font_family, 10 if compact else 11, "bold"),
        ).grid(row=0, column=1, sticky="w")
        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                bg=COLORS["card"],
                fg=COLORS["muted"],
                font=(self.ui_font_family, 8 if compact else 9),
            ).grid(row=1, column=1, sticky="w", pady=(1 if compact else 2, 0))

        body = tk.Frame(container, bg=COLORS["card"])
        body.grid(
            row=1, column=0, sticky="nsew",
            padx=12 if compact else 16,
            pady=(0, 6 if compact else 10),
        )
        return card, header, body

    def _section_icon(self, parent, kind):
        if not kind:
            return None
        size = self._px(ICON_SIZES["section"]["compact" if self.compact_ui else "normal"])
        canvas = tk.Canvas(parent, width=size, height=size, bg=COLORS["card"],
                           highlightthickness=0, bd=0)
        draw_icon(canvas, kind if kind in ("folder", "gear") else "terminal",
                  size/2, size/2, size, COLORS["primary"], "section_icon")
        return canvas

    def _form_icon(self, parent, kind, background=None):
        size = self._px(ICON_SIZES["field"]["compact" if self.compact_ui else "normal"])
        canvas = tk.Canvas(parent, width=size, height=size,
                           bg=background or parent.cget("bg"), highlightthickness=0, bd=0)
        draw_icon(canvas, kind, size/2, size/2, size, COLORS["primary"], "field_icon")
        return canvas

    def _create_checkbox(self, parent, text, variable, background=None):
        bg = background or COLORS["card"]
        container = tk.Frame(parent, bg=bg, cursor="hand2")
        box = tk.Canvas(
            container, width=self._px(18), height=self._px(18), bg=bg,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        box.pack(side=tk.LEFT)
        label = tk.Label(
            container,
            text=text,
            bg=bg,
            fg=COLORS["text"],
            font=(self.ui_font_family, 9),
            cursor="hand2",
        )
        label.pack(side=tk.LEFT, padx=(5, 0))

        def refresh(*_):
            selected = bool(variable.get())
            size = self._px(18)
            draw_rounded_rectangle(
                box, 1, 1, size-1, size-1, self._px(3),
                COLORS["primary"] if selected else bg,
                COLORS["primary"] if selected else COLORS["border"], tag="checkbox")
            box.delete("check")
            if selected:
                draw_icon(box, "check", size/2, size/2, size-3, "#FFFFFF", "check")

        def toggle(_event=None):
            variable.set(not bool(variable.get()))
            return "break"

        variable.trace_add("write", refresh)
        for widget in (container, box, label):
            widget.bind("<Button-1>", toggle)
        refresh()
        return container

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=COLORS["window"])
        self.form_container = outer
        outer.pack(
            fill=tk.BOTH, expand=True,
            padx=8 if self.compact_ui else 14,
            pady=(6, 12) if self.compact_ui else (10, 10),
        )
        outer.grid_columnconfigure(0, weight=2, minsize=self._px(740))
        outer.grid_columnconfigure(1, weight=1, minsize=self._px(330))
        outer.grid_rowconfigure(1, weight=1)
        main = tk.Frame(outer, bg=COLORS["window"])
        self.left_form = main
        main.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        header = tk.Frame(outer, bg=COLORS["window"])
        header.grid(
            row=0, column=0, columnspan=2, sticky="ew",
            pady=(0, 6 if self.compact_ui else 10),
        )
        logo = tk.Label(
            header,
            image=self.header_icon_image,
            bg=COLORS["window"],
            bd=0,
            highlightthickness=0,
        )
        logo.grid(
            row=0, column=0, rowspan=2, sticky="w",
            padx=(4 if self.compact_ui else 8, 8 if self.compact_ui else 12),
        )

        title_row = tk.Frame(header, bg=COLORS["window"])
        title_row.grid(row=0, column=1, sticky="sw")
        tk.Label(
            title_row,
            text="Python 运行打包工具",
            bg=COLORS["window"],
            fg=COLORS["text"],
            font=(self.ui_font_family, 15 if self.compact_ui else 18, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title_row,
            text=f"V{APP_VERSION}",
            bg=COLORS["window"],
            fg=COLORS["muted"],
            font=(self.ui_font_family, 10 if self.compact_ui else 11, "bold"),
        ).pack(
            side=tk.LEFT,
            padx=(8 if self.compact_ui else 12, 0),
            pady=(2 if self.compact_ui else 4, 0),
        )
        tk.Label(
            header,
            text="运行、调试和构建 Python 应用",
            bg=COLORS["window"],
            fg=COLORS["muted"],
            font=(self.ui_font_family, 8 if self.compact_ui else 9),
        ).grid(
            row=1, column=1, sticky="nw",
            pady=(1 if self.compact_ui else 2, 0),
        )

        file_card, _, file_body = self._create_card(
            main,
            0,
            "目标脚本",
            "",
            76 if self.compact_ui else 115,
            None,
        )
        file_body.grid_columnconfigure(0, weight=1)
        self.file_entry = RoundedEntry(
            file_body,
            textvariable=self.file_path_var,
            height=self._px(self.form_control_height),
            radius=self._px(9),
            background=COLORS["card"],
            parent_background=COLORS["card"],
            border=COLORS["border"],
            focus_border=COLORS["primary"],
            foreground=COLORS["text"],
            font=(self.ui_font_family, 9),
            left_padding=self._px(36),
            right_padding=self._px(34),
        )
        self.file_entry.grid(row=0, column=0, sticky="ew")
        self.file_entry.bind("<Return>", self._on_path_enter)
        self.file_entry.bind("<FocusIn>", self._refresh_file_placeholder)
        self.file_entry.bind("<FocusOut>", self._refresh_file_placeholder)
        self.file_placeholder = tk.Label(
            self.file_entry,
            text="选择要运行或打包的 Python 脚本文件，也可以直接粘贴文件或目录路径到这里",
            bg=COLORS["card"],
            fg="#9AA1AC",
            font=(self.ui_font_family, 9),
            cursor="xterm",
        )
        self.file_placeholder.bind("<Button-1>", self._focus_file_entry)
        self.file_path_var.trace_add("write", self._refresh_file_placeholder)
        self._decorate_file_entry()
        self._make_form_button(
            file_body, "浏览...", self.browse_file,
            kind="primary", icon_kind="file",
        ).grid(row=0, column=1, padx=(10, 0))
        self._make_form_button(
            file_body, "识别路径", self.resolve_script_input,
            icon_kind="search",
        ).grid(row=0, column=2, padx=(8, 0))
        self._refresh_file_placeholder()

        # Two input rows; the icon selector lives in the resource card.
        config_card_height = (
            (116 if self.compact_ui else 160)
            + round(max(0.0, self.ui_scale - 1.0) * 72)
        )
        config_card, _, config_body = self._create_card(
            main,
            1,
            "运行配置",
            "",
            config_card_height,
            None,
        )
        if self.compact_ui:
            config_card.grid_configure(pady=(0, 10))
        config_body.grid_columnconfigure(0, weight=1)

        config_left = tk.Frame(config_body, bg=COLORS["card"])
        config_left.grid(row=0, column=0, sticky="nsew")
        config_left.grid_columnconfigure(
            0, minsize=self._px(110 if self.compact_ui else 130)
        )
        config_left.grid_columnconfigure(1, weight=1)
        config_left.grid_columnconfigure(
            2, minsize=self._px(self.form_action_width + 8)
        )
        config_left.grid_columnconfigure(
            3, minsize=self._px(self.form_action_width + 8)
        )
        config_left.grid_rowconfigure(1, minsize=self._px(8 if self.compact_ui else 12))

        self._form_label(config_left, "Python 版本", 0, "python")
        compact_layout = self.window_width < 980
        self.python_select = RoundedSelect(
            config_left,
            variable=self.python_var,
            values=PYTHON_VERSIONS,
            width=self._px(160 if compact_layout else 230),
            height=self._px(self.form_control_height),
            radius=self._px(9),
            background=COLORS["card"],
            parent_background=COLORS["card"],
            border=COLORS["border"],
            focus_border=COLORS["primary"],
            foreground=COLORS["text"],
            muted=COLORS["muted"],
            font=(self.ui_font_family, 9),
        )
        self.python_select.grid(row=0, column=1, sticky="w")

        self._form_label(config_left, "所需依赖包", 2, "package")
        self.deps_entry = RoundedEntry(
            config_left,
            textvariable=self.deps_var,
            height=self._px(self.form_control_height),
            radius=self._px(9),
            background=COLORS["card"],
            parent_background=COLORS["card"],
            border=COLORS["border"],
            focus_border=COLORS["primary"],
            foreground=COLORS["text"],
            font=(self.ui_font_family, 9),
        )
        self.deps_entry.grid(row=2, column=1, columnspan=2, sticky="ew")
        self._make_form_button(
            config_left, "重新识别", self.reanalyze_imports,
            icon_kind="refresh",
        ).grid(row=2, column=3, padx=(10, 0))

        self.resource_panel = ResourcePanel(
            main, COLORS, self._px, (self.ui_font_family, 9), self._make_button,
            self._resource_script_path, self._resources_changed,
            self.icon_path_var.set,
        )
        self.resource_panel.grid(row=2, column=0, sticky="nsew", pady=(0, 6))

        action_card = RoundedFrame(
            outer,
            fill=COLORS["card"],
            background=COLORS["window"],
            border=COLORS["border_soft"],
            radius=self._px(10 if self.compact_ui else 12),
            height=self._layout_px(72 if self.compact_ui else 88),
        )
        action_card.grid(
            row=2, column=0, columnspan=2, sticky="ew",
            pady=(0, 0),
        )
        actions = tk.Frame(action_card.content, bg=COLORS["card"])
        self.action_card = action_card
        actions.pack(
            fill=tk.BOTH,
            expand=True,
            padx=10 if self.compact_ui else 14,
            pady=(7, 6) if self.compact_ui else (10, 8),
        )
        actions.grid_columnconfigure(3, weight=1)
        action_width = 145 if self.compact_ui else 170
        self.run_btn = self._make_button(
            actions, "▶  运行脚本", self.run_script,
            kind="primary", width=action_width,
            height=36 if self.compact_ui else 44,
        )
        self.run_btn.grid(row=0, column=0, sticky="w")
        self.pack_btn = self._make_button(
            actions, "▣  打包为 EXE", self.pack_exe,
            kind="secondary", width=action_width,
            height=36 if self.compact_ui else 44,
        )
        self.pack_btn.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.stop_btn = self._make_button(
            actions, "■  停止任务", self.stop_current_task,
            kind="danger", width=action_width,
            height=36 if self.compact_ui else 44,
        )
        self.stop_btn.set_state(tk.DISABLED)
        self.stop_btn.grid(row=0, column=2, sticky="w", padx=(10, 0))

        self.no_console_checkbox = self._create_checkbox(
            actions, "打包时隐藏控制台", self.no_console_var, background=COLORS["card"])
        self.no_console_checkbox.grid(row=0, column=3, sticky="w", padx=(20, 10))

        self.status_surface = RoundedFrame(
            actions,
            fill=COLORS["option_panel"],
            background=COLORS["card"],
            border=COLORS["border_soft"],
            radius=self._px(10),
            width=self._px(245 if self.compact_ui else 300),
            height=self._px(36 if self.compact_ui else 44),
        )
        self.status_surface.grid(row=0, column=4, sticky="e")
        status_box = self.status_surface.content
        self.status_dot = tk.Canvas(
            status_box,
            width=self._px(12 if self.compact_ui else 14),
            height=self._px(12 if self.compact_ui else 14),
            bg=COLORS["option_panel"],
            highlightthickness=0, bd=0,
        )
        self.status_dot.pack(
            side=tk.LEFT,
            padx=(8 if self.compact_ui else 10, 3 if self.compact_ui else 4),
            pady=6 if self.compact_ui else 8,
        )
        dot_size = int(self.status_dot.cget("width"))
        self._status_dot_id = draw_icon(self.status_dot, "dot", dot_size/2, dot_size/2,
                                        dot_size, COLORS["success"], "status_dot")
        self.status_label = tk.Label(
            status_box,
            textvariable=self.status_var,
            bg=COLORS["option_panel"],
            fg=COLORS["text"],
            font=(self.ui_font_family, 8, "bold"),
        )
        self.status_label.pack(side=tk.LEFT, pady=6 if self.compact_ui else 8)
        tk.Frame(status_box, width=1, height=16, bg=COLORS["border"]).pack(
            side=tk.LEFT, padx=9
        )
        self.status_version_label = tk.Label(
            status_box,
            textvariable=self.python_var,
            bg=COLORS["option_panel"],
            fg=COLORS["muted"],
            font=(self.ui_font_family, 8),
        )
        self.status_version_label.pack(
            side=tk.LEFT,
            padx=(0, 8 if self.compact_ui else 10),
            pady=6 if self.compact_ui else 8,
        )
        self.progress = RoundedProgressBar(
            actions,
            height=self._px(10 if self.compact_ui else 12),
            radius=self._px(6),
            background="#E7EDF5",
            foreground=COLORS["primary"],
            parent_background=COLORS["card"],
        )
        self.progress.grid(
            row=1, column=0, columnspan=5, sticky="ew",
            pady=(6 if self.compact_ui else 8, 0),
        )

        log_card, log_header, log_body = self._create_card(
            outer,
            1,
            "运行日志",
            "",
            204 if self.compact_ui else 260,
            None,
        )
        self.log_card = log_card
        log_card.grid_configure(column=1, sticky="nsew")
        if self.compact_ui:
            log_body.grid_configure(padx=8)
        log_card.content.grid_rowconfigure(1, weight=1)
        log_body.grid_rowconfigure(0, weight=1)
        log_body.grid_columnconfigure(0, weight=1)
        self._make_button(
            log_header, "清空日志", self.clear_log,
            kind="neutral", width=82 if self.compact_ui else 94,
            height=28 if self.compact_ui else 32,
        ).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        self._make_button(
            log_header, "复制日志", self.copy_log,
            kind="neutral", width=82 if self.compact_ui else 94,
            height=28 if self.compact_ui else 32,
        ).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        log_surface = RoundedFrame(
            log_body,
            fill=COLORS["log"],
            background=COLORS["card"],
            border=COLORS["log"],
            radius=self._px(7 if self.compact_ui else 9),
            height=self._px(154 if self.compact_ui else 180),
        )
        log_surface.grid(row=0, column=0, sticky="nsew")
        if self.compact_ui:
            log_surface.grid_configure(pady=(0, 8))
        log_surface.content.grid_rowconfigure(0, weight=1)
        log_surface.content.grid_columnconfigure(0, weight=1)
        self.log_area = tk.Text(
            log_surface.content,
            wrap=tk.WORD,
            bg=COLORS["log"],
            fg=COLORS["log_text"],
            insertbackground="#FFFFFF",
            selectbackground="#334155",
            selectforeground="#FFFFFF",
            font=(self.mono_font_family, 8 if self.compact_ui else 9),
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            padx=9 if self.compact_ui else 13,
            pady=7 if self.compact_ui else 10,
        )
        self.log_area.grid(row=0, column=0, sticky="nsew")
        self.log_scrollbar = RoundedScrollbar(
            log_surface.content,
            command=self.log_area.yview,
            width=self._px(14),
            background=COLORS["log"],
            track="#242428",
            thumb="#52525B",
            hover_thumb="#71717A",
        )
        self.log_scrollbar.grid(
            row=0, column=1, sticky="ns", padx=(2, 4), pady=5
        )
        self.log_area.configure(yscrollcommand=self.log_scrollbar.set)
        self._configure_log_tags()
        self.log(f"[*] Python运行打包工具V{APP_VERSION} 已启动。")

    def _form_label(self, parent, text, row, icon_kind):
        label_box = tk.Frame(parent, bg=COLORS["card"])
        label_box.grid(row=row, column=0, sticky="w", padx=(0, 14))
        self._form_icon(label_box, icon_kind).pack(
            side=tk.LEFT,
            padx=(0, 18 if self.compact_ui else 10),
        )
        tk.Label(
            label_box,
            text=text,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(self.ui_font_family, 9),
            anchor="w",
        ).pack(side=tk.LEFT)

    def _focus_file_entry(self, _event=None):
        self.file_entry.focus_set()

    def _decorate_file_entry(self):
        entry = self.file_entry
        self._position_file_entry_icon()
        tk.Canvas.bind(
            entry,
            "<Configure>",
            self._position_file_entry_clear,
            add="+",
        )
        tk.Canvas.bind(
            entry,
            "<Configure>",
            self._position_file_entry_icon,
            add="+",
        )
        self._position_file_entry_clear()

    def _position_file_entry_icon(self, _event=None):
        entry = self.file_entry
        height = max(entry.winfo_height(), self._px(self.form_control_height))
        draw_icon(entry, "file", self._px(19), height/2, self._px(20),
                  COLORS["muted"], "path_file_icon")

    def _position_file_entry_clear(self, _event=None):
        entry = self.file_entry
        entry.delete("path_clear")
        draw_icon(entry, "close", entry.winfo_width()-self._px(19), entry.winfo_height()/2,
                  self._px(16), COLORS["muted"], "path_clear")
        entry.tag_bind("path_clear", "<Button-1>", self._clear_script_path)
        entry.tag_bind("path_clear", "<Enter>", lambda _event: entry.configure(cursor="hand2"))
        entry.tag_bind("path_clear", "<Leave>", lambda _event: entry.configure(cursor="xterm"))
        self._refresh_file_clear_button()

    def _clear_script_path(self, _event=None):
        self.file_path_var.set("")
        self._selected_script_path = ""
        self.deps_var.set("")
        self.file_entry.focus_set()
        return "break"

    def _refresh_file_placeholder(self, *_):
        self._refresh_file_clear_button()
        if (
            not self.file_path_var.get()
            and self.root.focus_get() is not self.file_entry.entry
        ):
            self.file_placeholder.place(x=self._px(36), rely=0.5, anchor="w")
        else:
            self.file_placeholder.place_forget()

    def _refresh_file_clear_button(self):
        if not hasattr(self, "file_entry"):
            return
        if self.file_path_var.get():
            if not self.file_entry.find_withtag("path_clear"):
                self._position_file_entry_clear()
        else:
            self.file_entry.delete("path_clear")

    # ---------------- 日志 / UI 线程安全 ----------------

    def _configure_log_tags(self):
        self.log_area.tag_configure("info", foreground="#60A5FA")
        self.log_area.tag_configure("run", foreground="#2DD4BF")
        self.log_area.tag_configure("success", foreground="#4ADE80")
        self.log_area.tag_configure("warning", foreground="#F59E0B")
        self.log_area.tag_configure("error", foreground="#F87171")
        self.log_area.tag_configure("stdout", foreground=COLORS["log_text"])

    def _log_tag(self, message):
        lowered = message.lower()
        if "[系统错误]" in message or "异常退出" in message or "error" in lowered:
            return "error"
        if "[警告]" in message or "warning" in lowered:
            return "warning"
        if "成功" in message or "success" in lowered:
            return "success"
        if "开始 运行" in message or "开始 打包" in message or " run " in lowered:
            return "run"
        if message.startswith("[*]") or message.startswith("执行命令"):
            return "info"
        return "stdout"

    def log(self, message):
        message = str(message)
        self.log_area.insert(tk.END, message + "\n", self._log_tag(message))
        self.log_area.see(tk.END)

    def safe_log(self, message):
        self.root.after(0, self.log, message)

    def clear_log(self):
        self.log_area.delete("1.0", tk.END)

    def copy_log(self):
        content = self.log_area.get("1.0", "end-1c")
        if not content:
            self._set_status("暂无日志", "warning")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update_idletasks()
        self._set_status("日志已复制", "success")

    def _set_status(self, text, kind="ready"):
        colors = {
            "ready": COLORS["success"],
            "running": COLORS["primary"],
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["danger"],
        }
        self.status_var.set(text)
        size = int(self.status_dot.cget("width"))
        self._status_dot_id = draw_icon(self.status_dot, "dot", size/2, size/2, size,
                                        colors.get(kind, COLORS["success"]), "status_dot")

    def set_busy(
        self, busy, action_text="", status_text=None, status_kind="ready"
    ):
        def update():
            state = tk.DISABLED if busy else tk.NORMAL
            self.run_btn.set_state(state)
            self.pack_btn.set_state(state)
            self.stop_btn.set_state(tk.NORMAL if busy else tk.DISABLED)
            self.resource_panel.set_busy(busy)
            if busy:
                running_text = (
                    "正在构建 EXE..." if action_text == "打包 EXE" else "正在运行脚本..."
                )
                self._set_status(running_text, "running")
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate", value=0)
                self._set_status(status_text or "就绪", status_kind)
        self.root.after(0, update)

    # ---------------- 依赖分析 ----------------

    def analyze_imports(self, file_path):
        self._set_status("正在识别依赖...", "running")
        self.root.update_idletasks()
        try:
            analysis = analyze_imports(file_path)
            self.deps_var.set(" ".join(analysis.dependencies))
            if analysis.dependencies:
                self.log(f"[*] 自动识别到第三方依赖: {', '.join(analysis.dependencies)}")
            else:
                self.log("[*] 未检测到需要额外安装的第三方依赖。")
            if analysis.mappings:
                notes = [f"{source} → {target}" for source, target in analysis.mappings]
                self.log(f"[*] 包名映射: {', '.join(notes)}")
            if analysis.ignored_stdlib:
                self.log(f"[*] 已过滤标准库: {', '.join(analysis.ignored_stdlib)}")
            if analysis.ignored_local:
                self.log(f"[*] 已过滤本地模块/包: {', '.join(analysis.ignored_local)}")
            self._set_status("依赖识别完成", "success")
        except UnicodeDecodeError:
            self.log("[警告] 目标脚本不是 UTF-8 编码，自动依赖分析失败；可手动填写依赖。")
            self._set_status("依赖识别失败", "warning")
        except SyntaxError as exc:
            self.log(f"[警告] 目标脚本存在语法错误，无法自动分析依赖：{exc}")
            self._set_status("依赖识别失败", "warning")
        except Exception as exc:
            self.log(f"[警告] 自动分析依赖失败，可手动填写依赖。\n({exc})")
            self._set_status("依赖识别失败", "warning")

    def reanalyze_imports(self):
        previous_path = self._selected_script_path
        path = self.resolve_script_input()
        if not path:
            return
        if os.path.normcase(path) == os.path.normcase(previous_path):
            self.analyze_imports(path)

    # ---------------- 文件选择 / 校验 ----------------

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择要运行或打包的 Python 脚本",
            filetypes=[("Python Files", "*.py"), ("All Files", "*.*")],
        )
        if file_path:
            self._apply_script_selection(file_path)

    def _on_path_enter(self, _event):
        self.resolve_script_input()
        return "break"

    def resolve_script_input(self):
        """Resolve an editable path as a Python file or a directory of scripts."""
        raw_path = normalize_path_text(self.file_path_var.get())
        if not raw_path:
            messagebox.showwarning("提示", "请输入或粘贴 Python 脚本/目录路径。")
            return None

        path = Path(raw_path)
        if path.is_file():
            if path.suffix.lower() != ".py":
                messagebox.showerror("路径错误", "输入的文件不是 .py 格式的 Python 脚本。")
                return None
            return self._apply_script_selection(str(path))

        if not path.is_dir():
            messagebox.showerror("路径错误", f"输入的路径不存在：\n{raw_path}")
            return None

        try:
            scripts = list_python_scripts(str(path))
        except OSError as exc:
            messagebox.showerror("目录读取失败", f"无法扫描目录：\n{path}\n\n{exc}")
            return None

        if not scripts:
            messagebox.showwarning(
                "未找到脚本",
                f"该目录当前层级没有找到 .py 文件：\n{path}",
            )
            return None

        if len(scripts) == 1:
            selected = scripts[0]
            reason = "目录中只有一个 Python 脚本，已自动选中。"
        else:
            selected = find_preferred_script(scripts)
            reason = "检测到明确的 main 入口脚本，已自动选中。"
            if selected is None:
                selected = self._choose_script_dialog(path, scripts)
                reason = "已从目录脚本列表中选择目标脚本。"

        if selected is None:
            return None

        resolved = self._apply_script_selection(str(selected))
        self.log(f"[*] {reason}")
        return resolved

    def _apply_script_selection(self, script_path):
        resolved = os.path.abspath(script_path)
        changed = os.path.normcase(resolved) != os.path.normcase(
            self._selected_script_path
        )
        self.file_path_var.set(resolved)
        if changed:
            self._selected_script_path = resolved
            self.clear_log()
            self.log(f"已选择脚本: {resolved}")
            self.analyze_imports(resolved)
        return resolved

    def _choose_script_dialog(self, directory, scripts):
        dialog = tk.Toplevel(self.root)
        dialog.title("选择 Python 脚本")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.minsize(self._px(620), self._px(360))
        dialog.configure(bg=COLORS["window"])
        result = {"path": None}

        content = tk.Frame(
            dialog,
            bg=COLORS["card"],
            highlightbackground=COLORS["border_soft"],
            highlightthickness=1,
            bd=0,
        )
        content.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        tk.Label(
            content,
            text="目录中找到多个 Python 脚本，请选择目标脚本：",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(self.ui_font_family, 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(
            content,
            text=str(directory.resolve()),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(self.ui_font_family, 9),
            wraplength=self._px(720),
        ).pack(anchor="w", padx=16, pady=(3, 10))

        tree_frame = tk.Frame(content, bg=COLORS["card"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=16)
        tree = ttk.Treeview(
            tree_frame,
            columns=("modified", "size"),
            show="tree headings",
            selectmode="browse",
            style="Modern.Treeview",
        )
        tree.heading("#0", text="文件名")
        tree.heading("modified", text="修改时间")
        tree.heading("size", text="大小")
        metrics = tkfont.Font(root=dialog, font=(self.ui_font_family, 9))
        tree.column("#0", width=self._px(300), minwidth=self._px(180))
        tree.column("modified", width=max(self._px(150), metrics.measure("2000-00-00 00:00")+24),
                    anchor="center", stretch=False)
        tree.column("size", width=max(self._px(90), metrics.measure("1024.0 KB")+24),
                    anchor="e", stretch=False)
        scrollbar = RoundedScrollbar(
            tree_frame, command=tree.yview, width=self._px(12), background=COLORS["card"],
            track="#F3F6FA", thumb="#C9D2DE", hover_thumb="#98A2B3")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        paths = {}
        for index, script in enumerate(scripts):
            try:
                stat = script.stat()
                modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                size = f"{stat.st_size / 1024:.1f} KB"
            except OSError:
                modified = "-"
                size = "-"
            item_id = tree.insert(
                "", "end", text=script.name, values=(modified, size)
            )
            paths[item_id] = script
            if index == 0:
                tree.selection_set(item_id)
                tree.focus(item_id)

        def confirm(_event=None):
            selection = tree.selection()
            if selection:
                result["path"] = paths[selection[0]]
                dialog.destroy()

        def cancel():
            dialog.destroy()

        buttons = tk.Frame(content, bg=COLORS["card"])
        buttons.pack(fill=tk.X, padx=16, pady=(12, 14))
        self._make_button(
            buttons, "取消", cancel, kind="neutral", width=92, height=36
        ).pack(side=tk.RIGHT)
        self._make_button(
            buttons, "选择此脚本", confirm,
            kind="primary", width=124, height=36,
        ).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        tree.bind("<Double-1>", confirm)
        tree.bind("<Return>", confirm)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        dialog.update_idletasks()
        width = min(max(self._px(680), dialog.winfo_reqwidth()), dialog.winfo_screenwidth()-80)
        height = min(max(self._px(410), dialog.winfo_reqheight()), dialog.winfo_screenheight()-80)
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        tree.focus_set()
        self.root.wait_window(dialog)
        return result["path"]

    def _resource_script_path(self):
        return normalize_path_text(self.file_path_var.get()) or self._selected_script_path

    def _resources_changed(self, mappings):
        self.resource_mappings = list(mappings)

    def browse_icon(self):
        icon_path = filedialog.askopenfilename(
            title="选择 EXE 图标", filetypes=[("Windows 图标 (*.ico)", "*.ico")]
        )
        if icon_path:
            self.icon_path_var.set(icon_path)

    def _resolve_tool_window_icon(self):
        if os.name != "nt":
            return ""
        if getattr(sys, "frozen", False):
            return sys.executable
        source_icon = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "ico"
            / "Python_Tool_A2.ico"
        )
        return str(source_icon) if source_icon.is_file() else ""

    def _apply_tool_window_icon(self, icon_path):
        """Set this tool's own icon independently from the target EXE icon."""
        if os.name != "nt":
            return False
        try:
            self.root.iconbitmap(default=icon_path)
            self.root.iconbitmap(icon_path)
            return True
        except (tk.TclError, OSError) as exc:
            self.log(f"[警告] 窗口图标加载失败，保留当前图标：{exc}")
            return False

    def validate_icon(self):
        icon_path = self.icon_path_var.get().strip()
        if not icon_path:
            return ""
        if Path(icon_path).suffix.lower() != ".ico":
            messagebox.showerror("图标文件错误", "请选择 .ico 格式的图标文件。")
            return None
        if not os.path.isfile(icon_path):
            messagebox.showerror("图标文件错误", f"图标文件不存在或不是文件：\n{icon_path}")
            return None
        return os.path.abspath(icon_path)

    def check_uv(self):
        if is_uv_available():
            return True
        messagebox.showerror(
            "未找到 uv",
            "系统 PATH 中没有找到 uv。\n\n"
            "请先安装 uv，并确认在 CMD / PowerShell 中执行 `uv --version` 能正常输出。",
        )
        return False

    def get_python_version(self):
        return self.python_var.get().strip() or DEFAULT_PYTHON

    def validate_script(self):
        return self.resolve_script_input()

    # ---------------- 运行 / 打包 ----------------

    def run_script(self):
        script_path = self.validate_script()
        if not script_path or not self.check_uv():
            return
        command = build_run_command(
            script_path, self.get_python_version(), self.deps_var.get()
        )
        self.start_command(command, "运行脚本", script_path)

    def pack_exe(self):
        script_path = self.validate_script()
        if not script_path or not self.check_uv():
            return
        try:
            self.resource_panel.prepare(script_path)
            icon_path = self.validate_icon()
            if icon_path is None:
                return
            resources = validate_resources(self.resource_mappings, icon_path, script_path)
            command = build_pack_command(
                script_path, self.get_python_version(), self.deps_var.get(),
                self.no_console_var.get(), icon_path, resources,
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("资源配置错误", str(exc))
            return
        self.start_command(command, "打包 EXE", script_path, icon_path, resources)

    def start_command(self, command, action_name, script_path, icon_path="", resources=()):
        resources = tuple(resources)
        workdir = os.path.dirname(os.path.abspath(script_path)) or None
        context = None
        if action_name == "打包 EXE" and resources:
            context = partial(resource_build_context, script_path=script_path, resources=resources,
                              icon_path=icon_path, warning_callback=self.safe_log)
        elif action_name == "打包 EXE" and icon_path:
            context = partial(
                tkinter_icon_runtime_hook,
                icon_path=icon_path,
                warning_callback=self.safe_log,
            )
        self._stop_requested = False
        self.set_busy(True, action_name)
        started = self.process_runner.start(
            command=command,
            cwd=workdir,
            on_output=self.safe_log,
            on_started=partial(self._command_started, action_name, workdir, icon_path, resources=resources),
            on_finished=partial(self._command_finished, action_name, script_path, icon_path, resources=resources),
            command_context=context,
        )
        if not started:
            messagebox.showwarning("提示", "当前已有任务正在执行。")
            return

    def _command_started(self, action_name, workdir, icon_path, actual_command, resources=()):
        self.safe_log(f"\n========== 开始 {action_name} ==========")
        if action_name == "打包 EXE":
            self.safe_log(f"[*] EXE图标: {icon_path or '默认'}")
            self.safe_log("[*] 附加资源映射：" + ("" if resources else "无"))
            for resource in resources:
                self.safe_log(f"    {resource.source} -> {resource.destination}")
        self.safe_log(f"工作目录: {workdir}\n")
        if action_name == "打包 EXE" and icon_path:
            self.safe_log("[*] 已启用 Tkinter 窗口默认图标同步（无需修改目标脚本）。")
        self.safe_log(f"执行命令: {format_command(actual_command)}")

    def _command_finished(self, action_name, script_path, icon_path, result: ProcessResult, resources=()):
        final_status = "任务已停止" if self._stop_requested else "就绪"
        final_kind = "warning" if self._stop_requested else "ready"
        if result.error is not None:
            if isinstance(result.error, FileNotFoundError):
                self.safe_log(f"\n[系统错误] 找不到命令或文件：{result.error}\n")
            else:
                self.safe_log(
                    "\n[系统错误] 执行命令时发生异常：\n"
                    f"{type(result.error).__name__}: {result.error}\n"
                )
            if not self._stop_requested:
                final_status = "任务启动失败"
                final_kind = "error"
        elif result.return_code == 0:
            self.safe_log(f"\n========== {action_name} 成功完成! ==========\n")
            if action_name == "打包 EXE":
                self._log_cleanup_result(cleanup_pack_artifacts(script_path, icon_path, resources))
                final_status = "构建完成"
            else:
                final_status = "运行完成"
            final_kind = "success"
        else:
            self.safe_log(
                f"\n========== {action_name} 异常退出 "
                f"(代码: {result.return_code}) ==========\n"
            )
            if not self._stop_requested:
                final_status = "构建失败" if action_name == "打包 EXE" else "运行失败"
                final_kind = "error"
        self._stop_requested = False
        self.set_busy(False, status_text=final_status, status_kind=final_kind)

    def _log_cleanup_result(self, result):
        if result.removed:
            self.safe_log("[*] 已自动清理打包中间文件：")
            for item in result.removed:
                self.safe_log(f"    - {item}")
        elif result.warnings:
            self.safe_log("[*] 未删除中间文件；部分路径受资源保护或清理失败，原因如下。")
        else:
            self.safe_log("[*] 未发现需要清理的 build/.spec 中间文件。")
        for warning in result.warnings:
            self.safe_log(f"[警告] {warning}")
        self.safe_log("[*] dist 目录及最终 EXE 已保留。")

    def stop_current_task(self):
        try:
            self._stop_requested = True
            if self.process_runner.stop():
                self._set_status("正在停止任务...", "warning")
                self.log("[*] 已请求终止当前任务。")
            else:
                self._stop_requested = False
        except Exception as exc:
            self._stop_requested = False
            self.log(f"[警告] 终止任务失败：{exc}")
            self._set_status("停止失败", "error")


def center_window(root, width=900, height=690):
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def main():
    root = tk.Tk()
    UVToolApp(root)
    root.mainloop()
