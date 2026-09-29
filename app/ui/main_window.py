"""Tkinter user interface and application workflow orchestration."""

import os
import sys
import time
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ..constants import APP_TITLE, APP_VERSION, DEFAULT_PYTHON
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
    tkinter_icon_runtime_hook,
)
from ..services.uv_manager import build_run_command, is_uv_available
from ..utils.command import format_command


class UVToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(820, 580)

        self.file_path_var = tk.StringVar()
        self.icon_path_var = tk.StringVar()
        self.deps_var = tk.StringVar()
        self.python_var = tk.StringVar(value=DEFAULT_PYTHON)
        self.no_console_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="就绪")
        self.process_runner = ProcessRunner()
        self._selected_script_path = ""

        self._build_ui()
        tool_window_icon = (
            sys.executable if os.name == "nt" and getattr(sys, "frozen", False) else ""
        )
        self._apply_tool_window_icon(tool_window_icon)

    # ---------------- UI ----------------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_frame = ttk.LabelFrame(main, text="目标脚本", padding=8)
        file_frame.pack(fill=tk.X)
        ttk.Label(file_frame, text="Python 脚本路径：").grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4
        )
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var)
        file_entry.grid(
            row=0, column=1, sticky="ew", pady=4
        )
        file_entry.bind("<Return>", self._on_path_enter)
        file_buttons = ttk.Frame(file_frame)
        file_buttons.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=4)
        ttk.Button(
            file_buttons,
            text="识别路径",
            width=10,
            command=self.resolve_script_input,
        ).pack(side=tk.LEFT)
        ttk.Button(
            file_buttons, text="浏览...", width=10, command=self.browse_file
        ).pack(side=tk.LEFT, padx=(6, 0))
        file_frame.columnconfigure(1, weight=1)

        config_frame = ttk.LabelFrame(main, text="运行配置", padding=8)
        config_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(config_frame, text="Python 版本：").grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4
        )
        ttk.Combobox(
            config_frame,
            textvariable=self.python_var,
            values=["3.8.20", "3.9", "3.10", "3.11", "3.12", "3.13"],
            width=13,
        ).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Checkbutton(
            config_frame,
            text="打包 EXE 时隐藏控制台 (--noconsole)",
            variable=self.no_console_var,
        ).grid(row=0, column=2, columnspan=2, sticky="w", padx=(20, 0), pady=4)

        ttk.Label(config_frame, text="所需依赖包：").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4
        )
        ttk.Entry(config_frame, textvariable=self.deps_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=4
        )
        ttk.Button(
            config_frame,
            text="重新识别",
            width=10,
            command=self.reanalyze_imports,
        ).grid(
            row=1, column=3, sticky="w", padx=(8, 0), pady=4
        )
        ttk.Label(
            config_frame,
            text=(
                "支持空格/逗号分隔，可手动修改。程序会过滤标准库、"
                "本地模块，并自动把 serial 映射为 pyserial。"
            ),
            foreground="#666666",
        ).grid(row=2, column=1, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(config_frame, text="图标文件：").grid(
            row=3, column=0, sticky="e", padx=(0, 6), pady=4
        )
        ttk.Entry(config_frame, textvariable=self.icon_path_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=4
        )
        icon_buttons = ttk.Frame(config_frame)
        icon_buttons.grid(row=3, column=3, sticky="w", padx=(8, 0), pady=4)
        ttk.Button(
            icon_buttons, text="选择图标", width=10, command=self.browse_icon
        ).pack(side=tk.LEFT)
        ttk.Button(
            icon_buttons,
            text="清除图标",
            width=10,
            command=lambda: self.icon_path_var.set(""),
        ).pack(side=tk.LEFT, padx=(6, 0))
        config_frame.columnconfigure(2, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=12)
        self.run_btn = tk.Button(
            btn_frame, text="▶ 运行脚本 (Run)", bg="#4CAF50", fg="white",
            font=("Microsoft YaHei", 10, "bold"), width=19, command=self.run_script,
        )
        self.run_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.pack_btn = tk.Button(
            btn_frame, text="📦 打包为 EXE", bg="#2196F3", fg="white",
            font=("Microsoft YaHei", 10, "bold"), width=19, command=self.pack_exe,
        )
        self.pack_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = tk.Button(
            btn_frame, text="■ 停止任务", bg="#D9534F", fg="white",
            font=("Microsoft YaHei", 10, "bold"), width=14, state=tk.DISABLED,
            command=self.stop_current_task,
        )
        self.stop_btn.pack(side=tk.LEFT)
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side=tk.RIGHT)

        log_header = ttk.Frame(main)
        log_header.pack(fill=tk.X)
        ttk.Label(log_header, text="运行日志 (Console Output)：").pack(side=tk.LEFT)
        ttk.Button(log_header, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT)
        self.log_area = scrolledtext.ScrolledText(
            main, wrap=tk.WORD, bg="#1E1E1E", fg="#D4D4D4",
            insertbackground="white", font=("Consolas", 10),
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.log(f"[*] Python运行打包工具V{APP_VERSION} 已启动。")

    # ---------------- 日志 / UI 线程安全 ----------------

    def log(self, message):
        self.log_area.insert(tk.END, str(message) + "\n")
        self.log_area.see(tk.END)

    def safe_log(self, message):
        self.root.after(0, self.log, message)

    def clear_log(self):
        self.log_area.delete("1.0", tk.END)

    def set_busy(self, busy, action_text=""):
        def update():
            state = tk.DISABLED if busy else tk.NORMAL
            self.run_btn.config(state=state)
            self.pack_btn.config(state=state)
            self.stop_btn.config(state=tk.NORMAL if busy else tk.DISABLED)
            self.status_var.set(action_text if busy else "就绪")
        self.root.after(0, update)

    # ---------------- 依赖分析 ----------------

    def analyze_imports(self, file_path):
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
        except UnicodeDecodeError:
            self.log("[警告] 目标脚本不是 UTF-8 编码，自动依赖分析失败；可手动填写依赖。")
        except SyntaxError as exc:
            self.log(f"[警告] 目标脚本存在语法错误，无法自动分析依赖：{exc}")
        except Exception as exc:
            self.log(f"[警告] 自动分析依赖失败，可手动填写依赖。\n({exc})")

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
        dialog.minsize(560, 320)
        result = {"path": None}

        content = ttk.Frame(dialog, padding=12)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="目录中找到多个 Python 脚本，请选择目标脚本：",
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=str(directory.resolve()),
            foreground="#666666",
            wraplength=720,
        ).pack(anchor="w", pady=(2, 8))

        tree_frame = ttk.Frame(content)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(
            tree_frame,
            columns=("modified", "size"),
            show="tree headings",
            selectmode="browse",
        )
        tree.heading("#0", text="文件名")
        tree.heading("modified", text="修改时间")
        tree.heading("size", text="大小")
        tree.column("#0", width=300, minwidth=180)
        tree.column("modified", width=150, anchor="center")
        tree.column("size", width=90, anchor="e")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
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

        buttons = ttk.Frame(content)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="取消", command=cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="选择此脚本", command=confirm).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        tree.bind("<Double-1>", confirm)
        tree.bind("<Return>", confirm)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        dialog.update_idletasks()
        width = max(620, dialog.winfo_reqwidth())
        height = max(360, dialog.winfo_reqheight())
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        tree.focus_set()
        self.root.wait_window(dialog)
        return result["path"]

    def browse_icon(self):
        icon_path = filedialog.askopenfilename(
            title="选择 EXE 图标", filetypes=[("Windows 图标 (*.ico)", "*.ico")]
        )
        if icon_path:
            self.icon_path_var.set(icon_path)

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
        icon_path = self.validate_icon()
        if icon_path is None:
            return
        command = build_pack_command(
            script_path, self.get_python_version(), self.deps_var.get(),
            self.no_console_var.get(), icon_path,
        )
        self.start_command(command, "打包 EXE", script_path, icon_path)

    def start_command(self, command, action_name, script_path, icon_path=""):
        workdir = os.path.dirname(os.path.abspath(script_path)) or None
        context = None
        if action_name == "打包 EXE" and icon_path:
            context = partial(
                tkinter_icon_runtime_hook,
                enabled=True,
                warning_callback=self.safe_log,
            )
        self.set_busy(True, action_name)
        started = self.process_runner.start(
            command=command,
            cwd=workdir,
            on_output=self.safe_log,
            on_started=partial(self._command_started, action_name, workdir, icon_path),
            on_finished=partial(self._command_finished, action_name, script_path, icon_path),
            command_context=context,
        )
        if not started:
            messagebox.showwarning("提示", "当前已有任务正在执行。")
            return

    def _command_started(self, action_name, workdir, icon_path, actual_command):
        self.safe_log(f"\n========== 开始 {action_name} ==========")
        if action_name == "打包 EXE":
            self.safe_log(f"[*] EXE图标: {icon_path or '默认'}")
        self.safe_log(f"工作目录: {workdir}\n")
        if action_name == "打包 EXE" and icon_path:
            self.safe_log("[*] 已启用 Tkinter 窗口默认图标同步（无需修改目标脚本）。")
        self.safe_log(f"执行命令: {format_command(actual_command)}")

    def _command_finished(self, action_name, script_path, icon_path, result: ProcessResult):
        if result.error is not None:
            if isinstance(result.error, FileNotFoundError):
                self.safe_log(f"\n[系统错误] 找不到命令或文件：{result.error}\n")
            else:
                self.safe_log(
                    "\n[系统错误] 执行命令时发生异常：\n"
                    f"{type(result.error).__name__}: {result.error}\n"
                )
        elif result.return_code == 0:
            self.safe_log(f"\n========== {action_name} 成功完成! ==========\n")
            if action_name == "打包 EXE":
                self._log_cleanup_result(cleanup_pack_artifacts(script_path, icon_path))
        else:
            self.safe_log(
                f"\n========== {action_name} 异常退出 "
                f"(代码: {result.return_code}) ==========\n"
            )
        self.set_busy(False)

    def _log_cleanup_result(self, result):
        if result.removed:
            self.safe_log("[*] 已自动清理打包中间文件：")
            for item in result.removed:
                self.safe_log(f"    - {item}")
        else:
            self.safe_log("[*] 未发现需要清理的 build/.spec 中间文件。")
        for warning in result.warnings:
            self.safe_log(f"[警告] {warning}")
        self.safe_log("[*] dist 目录及最终 EXE 已保留。")

    def stop_current_task(self):
        try:
            if self.process_runner.stop():
                self.log("[*] 已请求终止当前任务。")
        except Exception as exc:
            self.log(f"[警告] 终止任务失败：{exc}")


def center_window(root, width=900, height=650):
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def main():
    root = tk.Tk()
    center_window(root)
    UVToolApp(root)
    root.mainloop()
