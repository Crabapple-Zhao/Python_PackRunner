# -*- coding: utf-8 -*-
"""
Python运行打包工具 V1.2

"""

import ast
import locale
import os
import pkgutil
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

APP_VERSION = "1.2"
APP_TITLE = f"Python运行打包工具 V{APP_VERSION}"
DEFAULT_PYTHON = "3.8.20"

# 仅在选择自定义图标时注入，不修改目标脚本。
TK_ICON_RUNTIME_HOOK = '# PyInstaller runtime hook: use the icon already embedded in the EXE.\nimport sys\nif sys.platform == "win32":\n    try:\n        import tkinter as tk\n    except ImportError:\n        pass\n    else:\n        original_init = tk.Tk.__init__\n        def init_with_exe_icon(self, *args, **kwargs):\n            original_init(self, *args, **kwargs)\n            if getattr(self, "_tkloaded", False):\n                try:\n                    self.iconbitmap(default=sys.executable)\n                    self.iconbitmap(sys.executable)\n                except (tk.TclError, OSError):\n                    pass\n        tk.Tk.__init__ = init_with_exe_icon\n'

# import 名称与 PyPI / uv 安装包名称不一致时，在这里做映射。
IMPORT_TO_PACKAGE = {
    "serial": "pyserial",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "Crypto": "pycryptodome",
    "nacl": "PyNaCl",
    "usb": "pyusb",
}

# Python 3.8 没有 sys.stdlib_module_names，因此保留一份兜底集合。
# 这里只是兜底，程序还会尝试从当前 Python 的 stdlib 路径动态扫描标准库。
STD_LIBS_FALLBACK = {
    "__future__", "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect",
    "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code",
    "codecs", "codeop", "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "csv", "ctypes", "curses", "dataclasses",
    "datetime", "dbm", "decimal", "difflib", "dis", "doctest", "email", "encodings",
    "ensurepip", "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "graphlib", "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os", "ossaudiodev",
    "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "pprint", "profile", "pstats", "pty", "pwd", "py_compile",
    "pyclbr", "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib", "resource",
    "rlcompleter", "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "ssl", "stat", "statistics", "string", "stringprep", "struct",
    "subprocess", "sunau", "symtable", "sys", "sysconfig", "tabnanny", "tarfile", "telnetlib",
    "tempfile", "termios", "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "trace", "traceback", "tracemalloc", "tty", "turtle", "turtledemo", "types",
    "typing", "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
    "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
    "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
}


def build_stdlib_set():
    """尽可能完整地构造标准库顶层模块集合，兼容 Python 3.8+。"""
    modules = set(sys.builtin_module_names) | set(STD_LIBS_FALLBACK)

    stdlib_names = getattr(sys, "stdlib_module_names", None)
    if stdlib_names:
        modules.update(stdlib_names)

    # Python 3.8 下尝试扫描当前解释器的标准库目录。
    try:
        stdlib_dir = sysconfig.get_path("stdlib")
        if stdlib_dir and os.path.isdir(stdlib_dir):
            for item in pkgutil.iter_modules([stdlib_dir]):
                modules.add(item.name)
    except Exception:
        pass

    return modules


STD_LIBS = build_stdlib_set()


def detect_local_modules(script_path):
    """识别目标脚本同目录下的本地 .py 模块和 Python 包，避免被当成 PyPI 依赖。"""
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


def normalize_dep_text(text):
    """允许空格、逗号、分号分隔依赖，并去重保序。"""
    raw = [x for x in re.split(r"[\s,;]+", text.strip()) if x]
    seen = set()
    result = []
    for dep in raw:
        key = dep.lower()
        if key not in seen:
            seen.add(key)
            result.append(dep)
    return result


def decode_process_line(data):
    """
    稳健解码子进程输出。

    uv 通常输出 UTF-8；旧版使用 text=True 时 Windows 会按本地 GBK 解码，
    从而出现：'gbk' codec can't decode byte ...
    """
    if isinstance(data, str):
        return data

    encodings = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(["gb18030", "cp936"])

    tried = set()
    for enc in encodings:
        key = enc.lower()
        if key in tried:
            continue
        tried.add(key)
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue

    return data.decode("utf-8", errors="replace")


def format_command(cmd_list):
    """仅用于日志显示，不参与真正执行。"""
    if os.name == "nt":
        return subprocess.list2cmdline(cmd_list)
    return shlex.join(cmd_list)


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

        self.current_process = None
        self.process_lock = threading.Lock()

        self._build_ui()
        self._default_window_icon = (
            sys.executable if os.name == "nt" and getattr(sys, "frozen", False) else ""
        )
        self._icon_preview_job = None
        self._apply_window_icon(self._default_window_icon)
        self.icon_path_var.trace_add("write", self._queue_icon_preview)

    # ---------------- UI ----------------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_frame = ttk.LabelFrame(main, text="目标脚本", padding=8)
        file_frame.pack(fill=tk.X)

        ttk.Label(file_frame, text="Python 脚本路径：").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=4
        )
        ttk.Button(file_frame, text="浏览...", command=self.browse_file).grid(row=0, column=2, padx=(8, 0), pady=4)
        file_frame.columnconfigure(1, weight=1)

        config_frame = ttk.LabelFrame(main, text="运行配置", padding=8)
        config_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(config_frame, text="Python 版本：").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        python_combo = ttk.Combobox(
            config_frame,
            textvariable=self.python_var,
            values=["3.8.20", "3.9", "3.10", "3.11", "3.12", "3.13"],
            width=13,
        )
        python_combo.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Checkbutton(
            config_frame,
            text="打包 EXE 时隐藏控制台 (--noconsole)",
            variable=self.no_console_var,
        ).grid(row=0, column=2, columnspan=2, sticky="w", padx=(20, 0), pady=4)

        ttk.Label(config_frame, text="所需依赖包：").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        ttk.Entry(config_frame, textvariable=self.deps_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(config_frame, text="重新识别", command=self.reanalyze_imports).grid(row=1, column=3, padx=(8, 0), pady=4)

        ttk.Label(
            config_frame,
            text=f"支持空格/逗号分隔，可手动修改。V{APP_VERSION} 会过滤标准库、本地模块，并自动把 serial 映射为 pyserial。",
            foreground="#666666",
        ).grid(row=2, column=1, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(config_frame, text="图标文件：").grid(row=3, column=0, sticky="e", padx=(0, 6), pady=4)
        ttk.Entry(config_frame, textvariable=self.icon_path_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=4
        )
        icon_buttons = ttk.Frame(config_frame)
        icon_buttons.grid(row=3, column=3, padx=(8, 0), pady=4)
        ttk.Button(icon_buttons, text="选择图标", command=self.browse_icon).pack(side=tk.LEFT)
        ttk.Button(icon_buttons, text="清除图标", command=lambda: self.icon_path_var.set("")).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        config_frame.columnconfigure(2, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=12)

        self.run_btn = tk.Button(
            btn_frame,
            text="▶ 运行脚本 (Run)",
            bg="#4CAF50",
            fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            width=19,
            command=self.run_script,
        )
        self.run_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.pack_btn = tk.Button(
            btn_frame,
            text="📦 打包为 EXE",
            bg="#2196F3",
            fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            width=19,
            command=self.pack_exe,
        )
        self.pack_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = tk.Button(
            btn_frame,
            text="■ 停止任务",
            bg="#D9534F",
            fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            width=14,
            state=tk.DISABLED,
            command=self.stop_current_task,
        )
        self.stop_btn.pack(side=tk.LEFT)

        ttk.Label(btn_frame, textvariable=self.status_var).pack(side=tk.RIGHT)

        log_header = ttk.Frame(main)
        log_header.pack(fill=tk.X)
        ttk.Label(log_header, text="运行日志 (Console Output)：").pack(side=tk.LEFT)
        ttk.Button(log_header, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT)

        self.log_area = scrolledtext.ScrolledText(
            main,
            wrap=tk.WORD,
            bg="#1E1E1E",
            fg="#D4D4D4",
            insertbackground="white",
            font=("Consolas", 10),
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
        """分析 import，尽量只留下真正需要由 uv / pip 安装的第三方依赖。"""
        try:
            # utf-8-sig 可以同时兼容普通 UTF-8 和带 BOM 的 UTF-8 文件。
            with open(file_path, "r", encoding="utf-8-sig") as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)

            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    # from .xxx import yyy 属于相对导入，不应视为第三方包。
                    if getattr(node, "level", 0) == 0:
                        imports.add(node.module.split(".")[0])

            local_modules = detect_local_modules(file_path)
            third_party = []
            ignored_stdlib = []
            ignored_local = []

            for pkg in sorted(imports, key=str.lower):
                if not pkg or pkg.startswith("_"):
                    continue
                if pkg in STD_LIBS:
                    ignored_stdlib.append(pkg)
                    continue
                if pkg in local_modules:
                    ignored_local.append(pkg)
                    continue
                third_party.append(pkg)

            resolved = []
            seen = set()
            mapped_notes = []
            for pkg in third_party:
                dep = IMPORT_TO_PACKAGE.get(pkg, pkg)
                if dep != pkg:
                    mapped_notes.append(f"{pkg} → {dep}")
                key = dep.lower()
                if key not in seen:
                    seen.add(key)
                    resolved.append(dep)

            self.deps_var.set(" ".join(resolved))

            if resolved:
                self.log(f"[*] 自动识别到第三方依赖: {', '.join(resolved)}")
            else:
                self.log("[*] 未检测到需要额外安装的第三方依赖。")

            if mapped_notes:
                self.log(f"[*] 包名映射: {', '.join(mapped_notes)}")
            if ignored_stdlib:
                self.log(f"[*] 已过滤标准库: {', '.join(ignored_stdlib)}")
            if ignored_local:
                self.log(f"[*] 已过滤本地模块/包: {', '.join(ignored_local)}")

        except UnicodeDecodeError:
            self.log("[警告] 目标脚本不是 UTF-8 编码，自动依赖分析失败；可手动填写依赖。")
        except SyntaxError as e:
            self.log(f"[警告] 目标脚本存在语法错误，无法自动分析依赖：{e}")
        except Exception as e:
            self.log(f"[警告] 自动分析依赖失败，可手动填写依赖。\n({e})")

    def reanalyze_imports(self):
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择 Python 脚本。")
            return
        self.analyze_imports(path)

    # ---------------- 文件选择 ----------------

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择要运行或打包的 Python 脚本",
            filetypes=[("Python Files", "*.py"), ("All Files", "*.*")],
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.clear_log()
            self.log(f"已选择脚本: {file_path}")
            self.analyze_imports(file_path)

    def browse_icon(self):
        icon_path = filedialog.askopenfilename(
            title="选择 EXE 图标",
            filetypes=[("Windows 图标 (*.ico)", "*.ico")],
        )
        if icon_path:
            self.icon_path_var.set(icon_path)

    def _apply_window_icon(self, icon_path):
        """Windows 可直接读取 ICO 或当前 EXE 中由 --icon 嵌入的资源。"""
        if os.name != "nt":
            return False
        try:
            self.root.iconbitmap(default=icon_path)
            self.root.iconbitmap(icon_path)
            return True
        except (tk.TclError, OSError) as exc:
            self.log(f"[警告] 窗口图标加载失败，保留当前图标：{exc}")
            return False

    def _queue_icon_preview(self, *_):
        # 同时支持文件选择和手工输入，避免每输入一个字符就加载图标。
        if self._icon_preview_job is not None:
            self.root.after_cancel(self._icon_preview_job)
        self._icon_preview_job = self.root.after(250, self._preview_window_icon)

    def _preview_window_icon(self):
        self._icon_preview_job = None
        icon_path = self.icon_path_var.get().strip()
        if not icon_path:
            self._apply_window_icon(self._default_window_icon)
        elif Path(icon_path).suffix.lower() == ".ico" and os.path.isfile(icon_path):
            self._apply_window_icon(os.path.abspath(icon_path))
        # 未完成或无效的输入不打断编辑；打包前仍由 validate_icon 提示。

    def validate_icon(self):
        """空字符串表示默认图标；None 表示校验失败。"""
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

    # ---------------- 命令构造 ----------------

    def check_uv(self):
        if shutil.which("uv"):
            return True
        messagebox.showerror(
            "未找到 uv",
            "系统 PATH 中没有找到 uv。\n\n请先安装 uv，并确认在 CMD / PowerShell 中执行 `uv --version` 能正常输出。",
        )
        return False

    def get_python_version(self):
        value = self.python_var.get().strip()
        return value or DEFAULT_PYTHON

    def get_uv_with_args(self):
        deps = normalize_dep_text(self.deps_var.get())
        args = []
        for dep in deps:
            args.extend(["--with", dep])
        return args

    def validate_script(self):
        script_path = self.file_path_var.get().strip()
        if not script_path:
            messagebox.showwarning("提示", "请先选择一个 Python 脚本！")
            return None
        if not os.path.isfile(script_path):
            messagebox.showerror("错误", "选择的 Python 脚本不存在。")
            return None
        return os.path.abspath(script_path)

    # ---------------- 运行 / 打包 ----------------

    def run_script(self):
        script_path = self.validate_script()
        if not script_path or not self.check_uv():
            return

        cmd = [
            "uv", "run",
            "--python", self.get_python_version(),
        ] + self.get_uv_with_args() + [script_path]

        self.start_command(cmd, "运行脚本", script_path)

    def cleanup_pack_artifacts(self, script_path, icon_path=""):
        """
        打包成功后清理 PyInstaller 中间产物。

        只删除当前脚本对应的：
        1. build/<脚本名>/ 构建目录；
        2. 当 build 已为空时，再删除空 build 目录；
        3. <脚本名>.spec 文件。

        dist 目录、最终 EXE 和本次使用的 ICO 源文件不删除。
        """
        script = Path(script_path).resolve()
        workdir = script.parent
        stem = script.stem

        removed = []
        warnings = []

        # PyInstaller 默认中间目录：build/<脚本名>/
        build_root = workdir / "build"
        target_build = build_root / stem

        # 使用本次命令的图标快照，不读取用户可能已修改的输入框。
        preserve_build = False
        if icon_path:
            try:
                Path(icon_path).resolve().relative_to(target_build.resolve())
                preserve_build = True
            except ValueError:
                pass

        try:
            if preserve_build:
                warnings.append(f"构建目录包含用户选择的 ICO，已保留：{target_build}")
            elif target_build.exists():
                shutil.rmtree(target_build)
                removed.append(str(target_build))
        except Exception as e:
            warnings.append(f"删除构建目录失败：{target_build} -> {e}")

        # 只有 build 已经为空时才删除根 build，避免误删其他项目内容。
        try:
            if build_root.exists() and build_root.is_dir():
                if not any(build_root.iterdir()):
                    build_root.rmdir()
                    removed.append(str(build_root))
        except Exception as e:
            warnings.append(f"删除空 build 目录失败：{build_root} -> {e}")

        # PyInstaller 默认 spec 文件：<脚本名>.spec
        spec_file = workdir / f"{stem}.spec"
        try:
            if spec_file.exists():
                spec_file.unlink()
                removed.append(str(spec_file))
        except Exception as e:
            warnings.append(f"删除 SPEC 文件失败：{spec_file} -> {e}")

        if removed:
            self.safe_log("[*] 已自动清理打包中间文件：")
            for item in removed:
                self.safe_log(f"    - {item}")
        else:
            self.safe_log("[*] 未发现需要清理的 build/.spec 中间文件。")

        for warning in warnings:
            self.safe_log(f"[警告] {warning}")

        self.safe_log("[*] dist 目录及最终 EXE 已保留。")

    def pack_exe(self):
        script_path = self.validate_script()
        if not script_path or not self.check_uv():
            return

        icon_path = self.validate_icon()
        if icon_path is None:
            return

        pyinstaller_args = ["pyinstaller", "--onefile"]
        if self.no_console_var.get():
            pyinstaller_args.append("--noconsole")
        if icon_path:
            pyinstaller_args.append(f"--icon={icon_path}")
        pyinstaller_args.append(script_path)

        cmd = [
            "uv", "run",
            "--python", self.get_python_version(),
            "--with", "pyinstaller",
        ] + self.get_uv_with_args() + pyinstaller_args

        self.start_command(cmd, "打包 EXE", script_path)

    def start_command(self, cmd, action_name, script_path):
        with self.process_lock:
            if self.current_process is not None:
                messagebox.showwarning("提示", "当前已有任务正在执行。")
                return

        self.set_busy(True, action_name)
        thread = threading.Thread(
            target=self.execute_command_thread,
            args=(cmd, action_name, script_path),
            daemon=True,
        )
        thread.start()

    def execute_command_thread(self, cmd_list, action_name, script_path):
        """后台执行命令；子进程输出以 bytes 读取，再自行解码，避免 Windows GBK 崩溃。"""
        self.safe_log(f"\n========== 开始 {action_name} ==========")

        icon_path = ""
        if action_name == "打包 EXE":
            icon_path = next((arg[len("--icon="):] for arg in cmd_list
                              if arg.startswith("--icon=")), "")
            self.safe_log(f"[*] EXE图标: {icon_path or '默认'}")

        workdir = os.path.dirname(os.path.abspath(script_path)) or None
        self.safe_log(f"工作目录: {workdir}\n")

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        hook_dir = None
        try:
            if action_name == "打包 EXE" and icon_path:
                # 临时钩子在整个打包进程结束后才清理；ICO 直接使用 EXE 内嵌资源。
                hook_dir = tempfile.TemporaryDirectory(prefix="python_tool_icon_")
                hook_path = Path(hook_dir.name) / "tk_window_icon.py"
                hook_path.write_text(TK_ICON_RUNTIME_HOOK, encoding="utf-8")
                cmd_list = list(cmd_list)
                cmd_list[-1:-1] = ["--runtime-hook", str(hook_path)]
                self.safe_log("[*] 已启用 Tkinter 窗口默认图标同步（无需修改目标脚本）。")
            self.safe_log(f"执行命令: {format_command(cmd_list)}")
            process = subprocess.Popen(
                cmd_list,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # 关键：不要 text=True。以 bytes 读取，自己做 UTF-8/GB18030 容错解码。
                text=False,
                bufsize=0,
                creationflags=creationflags,
            )

            with self.process_lock:
                self.current_process = process

            if process.stdout is not None:
                for raw_line in iter(process.stdout.readline, b""):
                    line = decode_process_line(raw_line).rstrip("\r\n")
                    if line:
                        self.safe_log(line)

            return_code = process.wait()

            if return_code == 0:
                self.safe_log(f"\n========== {action_name} 成功完成! ==========\n")
                if action_name == "打包 EXE":
                    self.cleanup_pack_artifacts(script_path, icon_path)
            else:
                self.safe_log(f"\n========== {action_name} 异常退出 (代码: {return_code}) ==========\n")

        except FileNotFoundError as e:
            self.safe_log(f"\n[系统错误] 找不到命令或文件：{e}\n")
        except Exception as e:
            self.safe_log(f"\n[系统错误] 执行命令时发生异常：\n{type(e).__name__}: {e}\n")
        finally:
            if hook_dir is not None:
                try:
                    hook_dir.cleanup()
                except OSError as exc:
                    self.safe_log(f"[警告] 图标临时钩子清理失败：{exc}")
            with self.process_lock:
                self.current_process = None
            self.set_busy(False)

    def stop_current_task(self):
        with self.process_lock:
            process = self.current_process

        if process is None:
            return

        try:
            process.terminate()
            self.log("[*] 已请求终止当前任务。")
        except Exception as e:
            self.log(f"[警告] 终止任务失败：{e}")


def center_window(root, width=900, height=650):
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


if __name__ == "__main__":
    root = tk.Tk()
    center_window(root)
    app = UVToolApp(root)
    root.mainloop()
