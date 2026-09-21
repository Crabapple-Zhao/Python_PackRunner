# Python运行打包工具（Python Tool）

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/%E5%BC%95%E6%93%8E-uv-de5c3c)
![Version](https://img.shields.io/badge/%E7%89%88%E6%9C%AC-V1.1-brightgreen)

一个基于 **tkinter + [uv](https://docs.astral.sh/uv/)** 的轻量级 Python 脚本运行与打包工具。
它能自动识别脚本依赖，并借助 uv 在隔离环境中完成依赖获取、脚本运行与 EXE 打包，让你彻底摆脱虚拟环境的管理烦恼。

> 当前版本：**V1.1**。历史版本变化请查看 [CHANGELOG.md](CHANGELOG.md)。

## 功能特性

- **自动依赖识别**：基于 `ast` 解析 import 语句，自动提取第三方依赖；智能过滤标准库（兼容 Python 3.8+）以及脚本同目录下的本地模块/包
- **包名智能映射**：自动将 import 名映射为正确的安装包名（如 `serial → pyserial`、`PIL → Pillow`），避免"找不到包"的问题
- **uv 无缝集成**：通过 `uv run` 在隔离环境中动态获取依赖并执行脚本，不污染系统环境
- **一键打包 EXE**：自动注入 pyinstaller 及所需依赖，打包为单文件 EXE；可选隐藏控制台窗口
- **自定义 EXE 图标**：选择原始 `.ico` 文件，打包时自动加入 `--icon`；支持中文、空格及括号路径，清除后恢复默认图标
- **多 Python 版本**：3.8.20 ~ 3.13 可选，默认 3.8.20，兼顾旧版 Windows 系统
- **实时日志窗口**：内置控制台实时显示运行/打包输出，后台异步刷新，界面不卡顿
- **任务控制**：支持中途停止任务、重新识别依赖、清空日志
- **自动清理**：打包成功后自动删除 build 中间目录与 `.spec` 文件，保留 `dist`、最终 EXE 与所选 ICO 源文件；若 ICO 位于待清理构建目录内，则保留该目录并提示

## 环境要求

使用本工具前，必须先安装 [uv](https://docs.astral.sh/uv/)（一款用 Rust 编写的极速 Python 包管理器），并确保其在系统环境变量 PATH 中。

**Windows 安装方法** —— 打开终端（Terminal 或 PowerShell）执行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

其他操作系统请参考 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

安装完成后，在终端执行 `uv --version`，能正常输出版本号即表示安装成功。

## 快速开始

### 方式一：下载 EXE 直接运行（推荐）

从本仓库的 [Releases](../../releases) 页面下载所需版本的 EXE（具体版本和文件名以发布页为准），双击即可运行（仍需提前安装 uv）。

### 方式二：源码运行

本工具的 GUI 仅使用 Python 标准库，克隆或下载本仓库后无需安装任何依赖，直接运行：

```bash
python Python_Tool_main.py
```

## 使用说明

1. 点击 **"浏览..."** 选择目标 `.py` 脚本，工具会自动分析 import 并填入识别到的第三方依赖；
2. 依赖输入框支持空格/逗号/分号分隔，可手动增删改；点击 **"重新识别"** 可随时重新分析；
3. 按需选择 Python 版本；如需命令行窗口，取消勾选 **"打包 EXE 时隐藏控制台"**（默认开启）；
4. 点击 **"▶ 运行脚本 (Run)"** 测试脚本；
5. 如需自定义 EXE 图标，点击 **"选择图标"** 选择 `.ico` 文件，也可在 **"图标文件"** 输入框填写路径；取消选择保持原设置，点击 **"清除图标"** 恢复默认图标。图标仅用于打包，不影响运行脚本；
6. 验证无误后点击 **"📦 打包为 EXE"**，生成的 EXE 将保存在目标脚本同目录下的 `dist` 文件夹中。

### import 名与安装包名映射表

| import 名 | 安装包名 |
| :---: | :--- |
| `serial` | `pyserial` |
| `cv2` | `opencv-python` |
| `PIL` | `Pillow` |
| `bs4` | `beautifulsoup4` |
| `sklearn` | `scikit-learn` |
| `yaml` | `PyYAML` |
| `dateutil` | `python-dateutil` |
| `dotenv` | `python-dotenv` |
| `Crypto` | `pycryptodome` |
| `nacl` | `PyNaCl` |
| `usb` | `pyusb` |

## 注意事项

- **打包参数**：默认使用 `pyinstaller --onefile`，且默认勾选 `--noconsole`。命令行工具可取消勾选隐藏控制台；如需附带资源文件，请修改源码中 `pack_exe` 函数的打包参数；
- **图标校验**：未选择图标时不添加 `--icon`；文件不存在、已删除、不是文件或后缀不是 `.ico` 时会阻止打包。当前不校验 ICO 内部数据完整性，损坏文件仍可能导致 PyInstaller 失败；
- **图标源文件**：直接使用所选文件的完整路径，不复制到 `build` 或 `dist`；打包期间请勿移动或删除该文件。日志会显示图标路径或“默认”；
- **工作目录**：运行/打包时会把工作目录切换到目标脚本所在目录，脚本中的相对路径资源可正常访问；
- **输出解码**：子进程输出按 UTF-8 优先解码，并兼容 GB18030/GBK，避免 Windows 下出现中文乱码或崩溃。

## 更新日志

历史版本变化请查看 [CHANGELOG.md](CHANGELOG.md)。
