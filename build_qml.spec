# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — BiliYTPlayer QML 版

用法（在仓库根目录）:
    python -m PyInstaller --noconfirm build_qml.spec
输出 dist/BiliYTPlayer.exe，与 mpv-portable/ 同级放置。

体积关键（ui-kit/README.md「打包注意事项」实测）：
  * PySide6 的 PyInstaller hook 会无差别收集全部 Qt DLL，`excludes` 对二进制无效，
    必须手动过滤 a.binaries。不做这步 → Qt6WebEngineCore.dll 单独 190 MB → exe 150 MB。
  * `FluentWinUI3/qmldir` 里 `import QtQuick.Controls.Fusion auto`，
    所以 Fusion **不能裁**（裁了运行时报 LOAD FAIL，静默无有用信息）；
    Basic **不能裁**（裁了 Fluent 控件回退到 Basic 实现）。
  * 实测：全收 150.21 MB / 只裁 WebEngine+Pdf 64.51 MB / 全裁 ≈48.8 MB。
"""

import sys
from pathlib import Path

_root = Path(SPECPATH).resolve()
_ui = _root / "ui"

_block_cipher = None

# ---- 动态 import，静态分析看不到 ----
_hidden_imports = [
    # 后端核心（bridge.py 内延迟 import）
    "bili_clipboard_dolby",
    "sponsorblock",
    "mpv_osc",
    "danmaku",
    "subtitle",
    # 新增应用层
    "app.app_config",
    "app.quality",
    "app.autostart",
    "app.tray",
    "ui.bridge",
    "ui.settings_bridge",
    # PySide6 子模块（QML 运行时按需 import，静态分析拿不全）
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtQml",
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "PySide6.QtCore",
    "PySide6.QtNetwork",
    # 平台后端（托盘菜单需要 widgets 平台插件）
    "pyperclip",
    # requests 底层
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
]

# ---- 随包分发的数据 ----
_add_datas = [
    # 后端模块源码（bridge 用 sys.path 从 legacy/ 导入）
    (str(_root / "legacy" / "bili_clipboard_dolby.py"), "legacy"),
    (str(_root / "legacy" / "sponsorblock.py"), "legacy"),
    (str(_root / "legacy" / "mpv_osc.py"), "legacy"),
    (str(_root / "legacy" / "danmaku.py"), "legacy"),
    (str(_root / "legacy" / "subtitle.py"), "legacy"),
    # OSC 补丁基线（缺了就退化为 mpv 内置 OSC）
    (str(_root / "legacy" / "osc_base.lua"), "legacy"),
    # 全部 QML（含 euikit 与 settings 子目录）
    (str(_ui), "ui"),
]

a = Analysis(
    ["bili_yt_player_qml.py"],
    pathex=[str(_root), str(_root / "legacy")],
    binaries=[],
    datas=_add_datas,
    hiddenimports=_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 标准库测试/文档
        "tkinter",          # QML 版不用 tkinter
        "test", "unittest", "pydoc", "doctest", "lib2to3", "distutils",
        # 明确不用的重型 Qt 模块（excludes 只影响 Python 模块，DLL 靠下面过滤）
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
        "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
        "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects",
        "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSpatialAudio",
        "PySide6.QtStateMachine", "PySide6.QtWebChannel",
        "PySide6.QtWebSockets", "PySide6.QtHttpServer",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=_block_cipher,
    noarchive=False,
)

# ============================================================
# 手动过滤 binaries —— 这一步决定 exe 是 48 MB 还是 150 MB
# ============================================================
#: 命中的 DLL / 目录一律丢弃（大小写不敏感）
_DROP_FRAGMENTS = [
    # 头像：WebEngine 单文件就 190 MB
    "qt6webengine", "qt6webview", "qt6webchannel", "qt6websockets", "qt6webenginecore",
    # PDF
    "qt6pdf",
    # 3D
    "qt6quick3d", "qt63d", "assimp",
    # Charts / 数据可视化
    "qt6charts", "qt6datavisualization",
    # 多媒体（播放全在 mpv，QML 侧不用）
    "qt6multimedia", "qt6spatialaudio",
    # 不用到的子系统
    "qt6bluetooth", "qt6nfc", "qt6positioning", "qt6serialport",
    "qt6sql", "qt6test", "qt6help", "qt6designer", "qt6uitools",
    "qt6remoteobjects", "qt6scxml", "qt6sensors", "qt6statemachine",
    "qt6httpserver",
    # 软件 OpenGL 兜底（8.8 MB，机器没有可用 GPU 时才有用；本程序不渲染 3D）
    "opengl32sw",
    # 插件目录里的重型后端
    "qtvirtualkeyboard", "qmltooling", "qt6virtualkeyboard",
]

#: 不能裁的样式（Fluent 依赖 Fusion 作为回退，Basic 是 Fluent 的实现基础）
_KEEP_STYLES = ("fusion", "basic", "fluentwinui3", "material", "universal", "imagine", "windows")

_kept, _dropped = [], []
for entry in a.binaries:
    dest = entry[0].lower().replace("\\", "/")
    if any(frag in dest for frag in _DROP_FRAGMENTS):
        _dropped.append(entry[0])
        continue
    _kept.append(entry)
a.binaries = _kept

# ============================================================
# 手动过滤 QtQuick/Controls 的样式目录（Material/Universal/Imagine/Windows 可裁）
# ============================================================
def _keep_qml_dir(dest: str) -> bool:
    """QtQuick/Controls/<Style> 下只保留 Fluent 需要的样式。"""
    low = dest.lower().replace("\\", "/")
    if "qtquick/controls/" in low:
        seg = low.split("qtquick/controls/", 1)[1].split("/")[0]
        if seg and seg not in _KEEP_STYLES:
            return False
    return True


_style_dropped = []


def _filter_style(entries):
    kept = []
    for entry in entries:
        if _keep_qml_dir(entry[0]):
            kept.append(entry)
        else:
            _style_dropped.append(entry[0])
    return kept


a.datas = _filter_style(a.datas)
a.binaries = _filter_style(a.binaries)

pyz = PYZ(a.pure, a.zipped_data, cipher=_block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BiliYTPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # --windowed：双击无控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="app.ico",
)

print(f"[build_qml] 丢弃 binaries {len(_dropped)} 项，丢弃样式/QML 目录 {len(_style_dropped)} 项")
