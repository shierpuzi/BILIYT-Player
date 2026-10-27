#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bili_yt_player_qml.py — 剪贴板直连播放器（PySide6 + QML 入口）

替换原 tkinter 入口 legacy/bili_yt_player.pyw 的 UI 层，业务层原样复用：
    剪贴板监听线程 + 工作线程（生产者-消费者）全部在 ui/bridge.py，
    UI 更新一律走 Qt Signal（等价原版的 root.after(0, ...)，跨线程自动排队）。

用法：
    python bili_yt_player_qml.py              # 正常启动
    python bili_yt_player_qml.py --autostart  # 开机自启：直接住托盘，不弹主窗口
"""

import sys

assert sys.version_info >= (3, 10), "需要 Python 3.10+"

import os
from pathlib import Path

# ---- PyInstaller --windowed 模式下 stdout/stderr 为 None，任何 print() 都会崩 ----
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
for _fh in (sys.stdout, sys.stderr):
    try:
        _fh.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# 无桌面（Linux 无 X / 远程会话）时给 Qt 一个明确的失败方式而不是静默卡住
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") \
        and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QTimer, QUrl, Property, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP_NAME = "BiliYTPlayer"
UI_DIR = Path(__file__).resolve().parent / "ui"


def _panic_log(exc: BaseException) -> Path:
    """启动失败时把 traceback 落到配置目录（--windowed 下看不到控制台）。"""
    import traceback
    log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{APP_NAME}_error.log"
    with open(log_path, "w", encoding="utf-8") as f:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    return log_path


def main() -> int:
    autostart_boot = "--autostart" in sys.argv

    # QQuickStyle 必须在 load() 之前设置（ui-kit/README.md:34-39）
    QQuickStyle.setStyle("FluentWinUI3")

    # 用 QApplication（不是 QGuiApplication）：托盘 QMenu 是 QWidget，
    # 没有 QApplication 时 QMenu() 会崩在 C++ 侧且无 Python 栈。
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("剪贴板直连播放器")
    app.setQuitOnLastWindowClosed(False)   # 最小化到托盘时窗口全隐藏也不能退出

    from ui.bridge import UiBridge

    bridge = UiBridge()
    # 必须让 bridge 的 PySide 包装对象活到 QML 引擎之后销毁。
    # setContextProperty 不接管所有权，若 bridge 只是个局部变量，解释器退出时
    # 会先回收它、再销毁 QML 引擎，于是所有 `bridge.xxx` 绑定在析构阶段报
    # "Cannot read property 'paused' of null"（实测，属于退出噪音但会淹掉真错误）。
    # 挂到 app 上让生命周期覆盖整个进程。
    app._dsh_bridge = bridge

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(UI_DIR))
    engine.rootContext().setContextProperty("bridge", bridge)

    # ---- 设置窗口（独立页面，settings-agent 交付）----
    settings_win = None
    settings_bridge = None
    try:
        from ui.settings_bridge import SettingsBridge
        settings_bridge = SettingsBridge(bridge.configDir(), log=bridge._log)
        # 同 bridge：保活到进程结束，避免析构阶段 QML 绑定读到 null
        app._dsh_settings_bridge = settings_bridge
        engine.rootContext().setContextProperty("settingsBridge", settings_bridge)
    except Exception as e:
        bridge._log(f"[!] 设置模块加载失败（设置页不可用）: {e}")

    # ---- 关闭询问框 ----
    close_dlg = None
    try:
        engine.load(QUrl.fromLocalFile(str(UI_DIR / "CloseDialog.qml")))
        if engine.rootObjects():
            close_dlg = engine.rootObjects()[-1]
    except Exception as e:
        bridge._log(f"[!] 关闭询问框加载失败: {e}")

    # ---- 主窗口 ----
    # 关键：engine.rootObjects() 是所有已加载的根对象，CloseDialog 已经在里面了。
    # 必须记下加载前的数量再取新增的那个，否则会拿成 CloseDialog，
    # 后面 win.show() 就会把关闭询问框弹出来（实测踩过）。
    _n_before = len(engine.rootObjects())
    engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
    _roots = engine.rootObjects()
    if len(_roots) <= _n_before:
        raise RuntimeError("Main.qml 加载失败（检查 ui/ 目录与 euikit 是否完整）")
    win = _roots[-1]
    assert win.property("title"), "Main.qml 根对象不是主窗口"

    if close_dlg is not None:
        try:
            close_dlg.setProperty("dialogParent", win)
        except Exception:
            pass
        win.setProperty("closeDialog", close_dlg)
        # 不要在 Python 侧 .connect 到 QML 的 function —— QML 的 function
        # 不是 Python 可调用属性。信号在 Main.qml 的 Connections 里接。

    # ---- 设置窗口：延迟加载，首次点「设置…」才创建 ----
    def _center_on(parent_win, child_win):
        """把 child 居中到 parent 上（两者都是 QQuickWindow，x/y 是屏幕坐标）。"""
        try:
            pg = parent_win.geometry()
            cg = child_win.geometry()
            child_win.setPosition(
                pg.x() + max(0, (pg.width() - cg.width()) // 2),
                pg.y() + max(0, (pg.height() - cg.height()) // 2),
            )
        except Exception:
            pass

    def open_settings(page: str = ""):
        nonlocal settings_win
        if settings_bridge is None:
            bridge.toast.emit("设置模块不可用")
            return
        if settings_win is None:
            engine.load(QUrl.fromLocalFile(str(UI_DIR / "settings" / "SettingsWindow.qml")))
            roots = engine.rootObjects()
            if not roots:
                bridge.toast.emit("设置页加载失败")
                return
            settings_win = roots[-1]
            try:
                settings_bridge.configChanged.connect(bridge.reloadConfigs)
            except Exception:
                pass

        if page:
            settings_win.setProperty("initialPage", page)
        # QML 里公开的 function open() 从 Python 调不到，用 visible 属性即可
        settings_win.setProperty("visible", True)
        try:
            settings_win.raise_()
            settings_win.requestActivate()
        except Exception:
            pass
        _center_on(win, settings_win)

    bridge.openSettingsRequested.connect(open_settings)

    # ---- 系统托盘 ----
    # 托盘信号一律转成 bridge 的信号，由 Main.qml 的 Connections 处理。
    # 不直接调 QML 函数，也不直接调 win.show() —— 让 QML 侧统一管窗口状态。
    tray = None
    try:
        from app.tray import Tray
        tray = Tray()
        if tray.available:
            tray.show()
            tray.showRequested.connect(bridge.trayShowRequested)
            tray.settingsRequested.connect(bridge.traySettingsRequested)
            tray.quitRequested.connect(bridge.trayQuitRequested)
            win.setProperty("tray", tray)
            tray.setTip("BiliYTPlayer — 复制链接即可播放")
        else:
            tray = None
            bridge._log("[*] 系统托盘不可用，关闭窗口将直接退出")
    except Exception as e:
        tray = None
        bridge._log(f"[!] 托盘初始化失败: {e}")

    # ---- 自启启动：不弹主窗口，只住托盘 ----
    if autostart_boot:
        bridge.minimizeToTrayRequested.emit()
        if tray:
            tray.notify(APP_NAME, "已在后台监听剪贴板，复制链接即可播放")
    else:
        win.show()

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:      # noqa: BLE001 — 顶层兜底，必须落盘
        try:
            p = _panic_log(e)
            print(f"[!] 启动失败，日志: {p}", file=sys.stderr)
        except Exception:
            pass
        raise
