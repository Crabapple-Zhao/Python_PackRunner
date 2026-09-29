"""Application-wide constants and static compatibility data."""

APP_VERSION = "2.0.0"
APP_TITLE = f"Python运行打包工具 V{APP_VERSION}"
DEFAULT_PYTHON = "3.8.20"

IMPORT_TO_PACKAGE = {
    "serial": "pyserial", "cv2": "opencv-python", "PIL": "Pillow",
    "bs4": "beautifulsoup4", "sklearn": "scikit-learn", "yaml": "PyYAML",
    "dateutil": "python-dateutil", "dotenv": "python-dotenv",
    "Crypto": "pycryptodome", "nacl": "PyNaCl", "usb": "pyusb",
}

# Python 3.8 没有 sys.stdlib_module_names，因此保留一份兜底集合。
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

TK_ICON_RUNTIME_HOOK = '''# PyInstaller runtime hook: use the icon already embedded in the EXE.
import sys
if sys.platform == "win32":
    try:
        import tkinter as tk
    except ImportError:
        pass
    else:
        original_init = tk.Tk.__init__
        def init_with_exe_icon(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if getattr(self, "_tkloaded", False):
                try:
                    self.iconbitmap(default=sys.executable)
                    self.iconbitmap(sys.executable)
                except (tk.TclError, OSError):
                    pass
        tk.Tk.__init__ = init_with_exe_icon
'''
