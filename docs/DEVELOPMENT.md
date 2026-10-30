# 开发与测试说明

## 源码结构

```text
.
├─ Python_Tool_main.py          # 启动入口
├─ app/
│  ├─ constants.py              # 版本和静态配置
│  ├─ core/                    # 依赖分析、进程管理和入口脚本识别
│  ├─ services/                # uv、PyInstaller、资源映射与校验
│  ├─ ui/                      # 界面、控件和图形资源
│  └─ utils/                   # 命令格式化与日志解码
├─ docs/                       # 文档、截图和工具图标
├─ scripts/                    # 开发资源生成脚本
└─ tests/                      # 资源与界面检查
```

`scripts` 和 `tests` 不参与程序启动。界面使用的生成资源保存在 `app/ui/_raster_masks.py`，作为 Python 模块随程序收录。

## 界面图形资源

图形定义位于 `scripts/generate_ui_masks.py`。生成器以 8 倍尺寸绘制图形，再缩小为不同显示尺寸的透明度蒙版。`app/ui/drawing.py` 使用标准库和 Tkinter 为蒙版着色、创建 PNG 并缓存图片；圆角通过固定四角和可伸展的平直区域拼接。

维护图形时，开发环境需要 Pillow，然后执行：

```bash
python scripts/generate_ui_masks.py
```

生成结果写入 `app/ui/_raster_masks.py`。普通源码运行和 EXE 使用无需 Pillow，也无需运行生成器。文字继续使用系统字体绘制。

## 打包工具本身

工具 ICO 位于 [docs/ico/Python_Tool_A2.ico](ico/Python_Tool_A2.ico)。使用本工具打包自身时，选择 `Python_Tool_main.py`，添加 `docs/ico` 资源目录，并在程序图标中选择该 ICO。

界面标识使用 `app/ui/assets.py` 中的内嵌 PNG。源码运行时优先使用仓库内的 ICO 设置工具窗口图标。

## 检查命令

在仓库根目录运行：

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python tests/resource_ui_check.py
python tests/drawing_quality_check.py
python tests/resource_collection_check.py
```

- `test_resources.py`：资源默认路径、去重、冲突、过滤、源文件保护和临时资源清理。
- `resource_ui_check.py`：资源编辑、图标选择、路径重算、任务状态和列表滚动，需要可用桌面。
- `drawing_quality_check.py`：图形资源、控件状态、图片缓存、窗口缩放和高 DPI 显示，需要可用桌面。
- `resource_collection_check.py`：使用开发环境中的 PyInstaller 检查参数解析和数据收录，不构建 EXE。

检查时使用临时目录和测试数据，不应修改其他项目或用户源资源。源码检查不能替代目标 Windows 系统上的 EXE 构建与运行检查。

## 资源打包实现

资源映射、默认路径和冲突校验位于 `app/services/resources.py`。`app/services/pyinstaller_backend.py` 沿用现有命令构造，为每个映射添加独立的 `--add-data` 参数。

需要过滤缓存或构建产物的目录会复制到工具临时目录中，副本在整个构建过程中保持有效，结束后清理。用户源目录不作为临时目录删除。

选择程序图标时，保留 `--icon` 设置 EXE 文件图标，并将 ICO 副本以 `python_tool_window_icon.ico` 收录。Tkinter runtime hook 从 `sys._MEIPASS` 加载该 ICO。临时图标、hook 和资源副本均由构建上下文管理。
