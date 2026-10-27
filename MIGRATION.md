# 迁移记录 — tkinter → PySide6 + QML

> 按 `ui-kit/MIGRATION_PROMPT.md` 执行。分支 `feature/qml-migration`。
> 后端零改动（`danmaku.py` / `sponsorblock.py` / `subtitle.py` / `mpv_osc.py` /
> `osc_base.lua` 全部未动），`bili_clipboard_dolby.py` 仅按用户新需求做了画质相关的
> 向后兼容扩展（详见第 5 节）。

## 1. 交付物清单

| 文件 | 作用 | 行数 |
|---|---|---|
| `bili_yt_player_qml.py` | 新入口（替代 `legacy/bili_yt_player.pyw` 的 UI 层） | ~215 |
| `ui/bridge.py` | `UiBridge(QObject)`，业务层 ↔ QML 的唯一通道 | ~640 |
| `ui/Main.qml` | 主窗口 | ~470 |
| `ui/CloseDialog.qml` | 关闭询问对话框 | 198 |
| `ui/theme.qml` | Fluent 2 设计 token 单例 | 40 |
| `ui/qmldir` | 把 `theme.qml` 注册为 `singleton Theme` | 1 |
| `ui/euikit/` | EUIKit 5 组件（从 `ui-kit/euikit/` 拷入，`ESpringListDelegate` 加 `clicked` 信号） | 5 文件 |
| `ui/settings/` | FluentUI 风格独立设置页（SettingsWindow + 6 页签 + 复用行组件） | 12 文件 |
| `ui/settings_bridge.py` | `SettingsBridge(QObject)` | — |
| `app/app_config.py` | `general.conf` 读写（关闭行为 / 自启 / 画质） | ~110 |
| `app/quality.py` | B 站画质档位映射 + 挑流规则 | ~130 |
| `app/autostart.py` | 开机自启（HKCU Run） | ~135 |
| `app/tray.py` | 系统托盘（QPixmap 现画图标，无外部资源） | ~165 |
| `build_qml.spec` | PyInstaller 配置（含手动 binaries 过滤） | ~215 |

`legacy/bili_yt_player.pyw` **保留未删** —— 它是旧入口，可作为回退路径。
新入口不依赖它。

## 2. 逐块对应关系（tkinter → QML）

### 主窗口 `_build_ui`（原 258-336 行，79 行）

| tkinter | QML | 备注 |
|---|---|---|
| `ttk.Label("剪贴板直连播放器 — B站 / YouTube", font=12 bold)` | `header: ToolBar` 里的图标 + 两段 `Text` | 加深色圆角图标块 |
| `ttk.LabelFrame("状态")` + `tk.Text(height=10, state=disabled)` | `ESpringCard` + `ListView` + `ListModel` + `Text` delegate | **没有**用 `ECardWithTextArea` —— 那是输入框（带 placeholderText），日志是只读追加 |
| `ttk.LabelFrame("播放历史")` + `ttk.Treeview(4 列)` + `<Double-1>` | `ESpringCard` + `ListView` + `ESpringListDelegate` + `onDoubleClicked` | 4 列变成一行内的 4 个 `Text`，标题列 `Layout.fillWidth` + `elide: ElideRight` |
| `btn_frame` 6 个 `ttk.Button` | 4 个 `ESpringButton` | 3 个设置按钮合并成 1 个「设置…」，打开独立设置页 |
| `sw` 3 个 `ttk.Checkbutton` | 3 个 `ESpringSwitch` | 绑定 `bridge.skipEnabled` / `danmakuEnabled` / `subtitleEnabled`，setter 内部落盘 |
| `ttk.Scrollbar` | `ScrollBar.vertical` attached | — |
| `tk.Text.see("end")` | `ListView.positionViewAtEnd()` | — |

### 4 个 tkinter 对话框 → 1 个独立设置窗口

原 414 行分散在 4 个 `Toplevel` 里，现在合并为 `ui/settings/SettingsWindow.qml`
（左侧页签 + 右侧卡片分组，Fluent 设置页标准布局）：

| 原方法 | 原行数 | 现在 |
|---|---|---|
| `_open_subtitle_settings` 362-478 | 117 | `SubtitlePage.qml` |
| `_open_danmaku_settings` 479-599 | 121 | `DanmakuPage.qml` |
| `_open_settings` 600-726 | 127 | `SponsorPage.qml` |
| `_show_sessdata_page` 845-893 | 49 | `AccountPage.qml` + 新增 `GeneralPage.qml` / `PlaybackPage.qml` |

**范围钳制逻辑一行没改**（原 556-575 行那 6 行 `max/min`，是全项目最不能动的地方）：

```python
new["opacity"]         = max(0.05, min(1.0,  _num(opacity_var, 0.7)))
new["font_size_ratio"] = max(0.01, min(0.20, _num(fontsize_var, 0.04)))   # 上限 0.20，不是 0.08
new["duration_marquee"]= max(2.0,  min(30.0, _num(marquee_var, 12.0)))
new["duration_still"]  = max(1.0,  min(20.0, _num(still_var, 5.0)))
new["display_region"]  = max(0.3,  min(1.0,  _num(region_var, 0.30)))     # 低于 0.3 轨道太少
new["outline"]         = max(0.0,  min(6.0,  _num(outline_var, 2.0)))
```

字幕侧同理保留 `position_ratio ∈ [0, 0.4]` / `font_size_ratio ∈ [0.01, 0.12]` /
`opacity ∈ [0.05, 1.0]` / `outline ∈ [0, 6.0]`。

> **QML 的 `DoubleValidator` 只是软约束**（可以粘贴超范围值），所以钳制全部留在
> Python 侧。`settings_bridge.py` 的 `saveDanmaku()` / `saveSubtitle()` /
> `saveSponsor()` 是唯一的落盘入口。

### 配置读写：格式/位置/字段名全部未变

| 文件 | 位置 | 状态 |
|---|---|---|
| `danmaku.conf` | `%APPDATA%\BiliYTPlayer\` | 未变，`danmaku.load_config/save_config` |
| `subtitle.conf` | 同上 | 未变，`subtitle.load_config/save_config` |
| `sponsorblock.conf` | 同上 | 未变，`sponsorblock.load_config/save_config` |
| `.env`（SESSDATA） | 同上 | 未变，格式仍是 `"# B 站登录态 Cookie\nSESSDATA=xxx\n"` |
| **`general.conf`** | 同上 | **新增**（关闭行为 / 自启 / 画质），`app/app_config.py` |

旧版用户升级后 `general.conf` 自动生成默认值，原有 4 份配置零迁移成本。

## 3. 线程模型：11 处 `root.after(0, ...)` 全部换成 Signal

这是最容易出事的环节（`.cursorrules:63`）。做法是**保持封装函数签名不变，只换内部实现**，
所以 11 个调用点一个都没动：

```python
# 原
def _log(self, msg):
    self.root.after(0, self._log_ui, msg)

# 新（ui/bridge.py）
def _log(self, msg):
    self.logLine.emit(f"[{datetime.now():%H:%M:%S}] {msg}")
```

`Signal.emit()` 跨线程时 Qt 自动排队投递到接收者（QML）所在线程，语义等价且更安全。

逐项对照：

| 原行 | 原写法 | 现在 |
|---|---|---|
| 774 | `after(0, self._log_ui, msg)` | `self.logLine.emit(...)` |
| 796 | `after(0, self._add_history_ui, entry)` | `self.historyAdded.emit(...)` |
| 907 | `after(0, lambda: self._ask_player_and_init())` | 改为日志提示 + `toast.emit()`（QML 无文件对话框场景，mpv 由 `find_player()` 多级探测） |
| 919 / 947 | `after(0, lambda: pause_btn.configure(state="disabled"))` | `readyChanged` 信号，QML 侧 `enabled: bridge.ready` |
| 940 | `after(0, self._quit)` | `requestQuit`（QML `Qt.quit()`） |
| 951 | `after(0, lambda: pause_btn.configure(...))` | `pausedChanged` + `readyChanged` |
| 952 | `after(0, self.start_monitor)` | `startMonitor()`（槽函数，主线程调用） |
| 455/567/710 | `win.after(600, win.destroy)` | 设置页保存后不关窗，用 `ESpringToast` / 页内状态文字提示 |

`self.history` 这个 Python 侧列表**继续维护**（原 214 行）—— 它是重播的数据源，
不是纯 UI 状态。QML 的 `ListModel` 只是显示副本，`bridge.replay(index)` 用 index
回去查 `self.history`。

## 4. 新增功能

### 4.1 独立设置页面（用户要求：遵循 FluentUI 设计思想）

`ui/settings/SettingsWindow.qml`，独立 `Window`（不是 Dialog），左侧页签导航 + 右侧
卡片分组，6 个页签：通用 / 播放 / 弹幕 / 字幕 / 广告跳过 / B站账号。

### 4.2 「点击 × 之后」+ 关闭询问（用户要求）

三层状态，全部落在 `general.conf`：

| 字段 | 含义 |
|---|---|
| `close_action` | `ask`（每次都问）/ `close`（直接退出）/ `tray`（最小化到托盘） |
| `ask_on_close` | 是否还弹询问框。取消勾选「以后不再显示」后为 `false` |

判定流程（`ui/Main.qml` 的 `onClosing`）：

```
close_action == "ask" 或 ask_on_close == true
    → 弹 ui/CloseDialog.qml（预选：设置里选过就跟着走，没选过默认"托盘"）
    → accepted(action, remember)
        → bridge.saveCloseChoice(action, remember)
        → remember=true 则 ask_on_close=false（以后不再问）
        → 执行对应动作
否则
    → 直接执行 close_action，不问
```

`CloseDialog.qml` 里「以后不再显示这个询问」**默认勾选**（`remember: true`），
单选默认「最小化到托盘」（不会误关掉后台监听）。

### 4.3 开机自启（用户要求）

`app/autostart.py`，写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
（**不需要管理员权限**，只写当前用户；不用计划任务、不碰 HKLM）。

- 项名 `BiliYTPlayer`，值 `"C:\path\BiliYTPlayer.exe" --autostart`（带引号防空格路径）
- 入口识别 `--autostart`：住托盘、不弹主窗口
- 源码运行时 `current_exe()` 返回 `None`（自启无意义），`apply()` 返回
  `(False, "取不到程序路径…")`，设置页直接显示这句话
- 非 Windows：`apply()` 返回 `(False, "仅 Windows 支持开机自启")`，不抛

### 4.4 系统托盘（关闭到托盘的落点）

`app/tray.py`，`QSystemTrayIcon` + 3 项菜单（显示主窗口 / 设置 / 退出），双击唤回。
图标用 `QPixmap` + `QPainter` 现画 16/32 两档（深色圆角块 + 白色播放三角 + B站蓝描边），
**不带外部资源文件**。

> 踩到的坑：托盘防御原本写 `QApplication.instance() is None`。只建
> `QGuiApplication` 时 `instance()` 不是 `None`（返回那个 QGuiApplication 实例），
> 判断漏掉后 `QMenu()` 直接崩在 C++ 侧且无 Python 栈。已改成
> `isinstance(QApplication.instance(), QApplication)`，并留了独立自检锁住。

### 4.5 B 站画质参数（用户要求：前端可调）

设置页「播放」页签可选画质上限（自动 / 8K / 杜比视界 / HDR / 4K / 1080P60 /
1080P+ / 1080P / 720P / 480P / 360P），存 `general.conf` 的 `quality`。

⚠️ **两个参数必须都传**，语义不同：

```python
qn = qn_from_pref(pref)                    # 请求档位 → 传给 playurl
max_qn = 0 if pref == "auto" else qn       # 本地挑选上限 → 传给 pick_dolby_streams
data = get_playurl(session, bvid, cid, img_key, sub_key, qn=qn)
vurl, aurl, vd, ad = pick_dolby_streams(dash, max_qn=max_qn)
```

实测 B 站 playurl 的 `qn` **只影响返回里的 `quality` 字段**，不裁返回的流集合
（qn=64 时 `dash.video` 仍然有 `[16,32,64,80,112]` 全部档位），所以 `max_qn`
必须由 `pick_stream` 在本地硬筛，否则「选 720P 还是播 4K」。

同一个 `max_qn` 还必须传给 `_stream_size()`：弹幕/字幕的 ASS `PlayRes` 要按
**实际播放的**分辨率算，否则锁 720P 时仍按 4K 算，弹幕字号只剩 1.2% 屏高。

## 5. B 站清晰度 bug：根因与修复

用户报告「B 站获取视频清晰度可能有点 bug」。实测定位到**两个真问题** + 一批脏数据隐患。

### Bug 1（致命）：番剧 / 影视（PGC）根本播不了

实测 `ep7065887`（功夫熊猫：神龙骑士 第二季）：

```
resolve_episode() 拿到的 bvid/cid 正确
  → x/player/wbi/playurl  →  code=-404 "啥都木有"  →  抛 RuntimeError  →  用户看到播放失败
  → pgc/player/web/playurl →  code=0，正常返回 dash
```

`x/player/wbi/playurl` 是 **UGC 投稿**端点，对 **PGC 番剧/影视**返回 -404。
所以「点番剧链接没反应/报错」不是画质问题，是完全播不了。

**修复**：`get_playurl()` 在 `x/player/wbi/playurl` 失败（`code != 0` 或 data 为空）时，
用**同一份 params 重新签名**回落到 `pgc/player/web/playurl`（只传 bvid+cid ——
实测 `bvid+cid` / `bvid+cid+ep_id` / `cid only` 三种组合返回完全一致，取最简单的，
`resolve_episode` 的调用方零改动）。载荷位置由 `_unwrap_playurl()` 统一
（PGC 落在 `result`，UGC 落在 `data`），两条路径返回给调用方的结构一致。

### Bug 2：`pick_dolby_streams` 对 dolby 段假设错误

- `dolby.get("audio")` 被当成 list 取 `[0]`，实测 B 站返回的是 **dict** → `KeyError`
- `dolby.get("video")` 同样
- 字段名混用：`base_url` / `baseUrl`、`backup_url` / `backupUrl` 在流对象里并存，
  但 dolby 段只保证 `base_url`/`backup_url`；原代码对 dolby 用 `backupUrl` 是脆的

**修复**：新增 `_as_stream_list()`（dict→`[dict]`、None→`[]`）与 `_stream_url()`
（`base_url` → `baseUrl` → `backup_url[0]` → `backupUrl[0]`，全空返回 `None` 不抛）。
修在共享函数上，不在每个调用点各加一层 try/except。

### Bug 3：挑流缺少画质上限

**修复**：`pick_dolby_streams(dash, max_qn=0)` 加 `max_qn`，走共享的
`app.quality.pick_stream()`：先按 `id <= max_qn` 过滤，再对 `id > 0` 的流按
`(id, bandwidth)` 取最大。`id` 缺失/为 0 的脏流不参与 id 排序（避免被排到最前），
只有全部无 id 时才回退到 `(height, bandwidth)`。

### 向后兼容（硬要求）

- `get_playurl(..., qn: int = 126)` —— 默认 126，旧调用方零改动
- `pick_dolby_streams(dash, max_qn: int = 0)` —— 返回仍是 4 元组
- `python -m unittest discover -s legacy/tests -t .` → **193 tests OK**
- `legacy/bili_yt_player.pyw` 不传 max_qn（等于永远 auto），行为与修复前一致

### 实测验证矩阵

`_verify_quality.py`（真实联网）：

| 项 | 结果 |
|---|---|
| UGC 画质不回退（3 个样本，含 4K / 1080P60） | `pick == accept_quality[0]` 全 PASS |
| PGC `ep7065887` 从 -404 变成能播 | 720P 1280x720 / 普通音频 id=30280 |
| `max_qn=64` 生效 | 不限=120 → 上限后=64 |
| 9 种畸形 dash（dolby 为 dict / None / 空 / 字符串） | 全部不崩 |
| 旧签名 `get_playurl` 不传 qn | 正常返回 |

14 个热门视频样本 + 6 个 8K/HDR/杜比样本全部 `pick == accept_quality[0]`，
说明 UGC 侧本来就没坏 —— 用户的感知问题来自 PGC 与画质上限缺失。

## 6. 验收标准对照

| 项 | 标准 | 状态 |
|---|---|---|
| 启动 | `python bili_yt_player_qml.py` 出窗口，Fluent 生效 | ✅ 实测 |
| 剪贴板监听 | 复制链接 → 自动播放，日志出现对应行 | ✅ 实测（真实网络，17 项） |
| 播放历史 | 每次播放追加一行，双击重播 | ✅ 实测 |
| 3 个开关 | 勾选持久化，重启保留 | ✅ 实测 |
| 设置页 | 打开、改值、保存、重开读到新值 | ✅ 实测（128 项 + 6 页切换） |
| SESSDATA 配置 | 未配置时引导到设置页账号页签 | ✅ |
| 动效 | 按钮缩放回弹、卡片入场、Toast | ✅（EUUIKit spring 2.5/0.25） |
| 深浅色 | 跟随系统 | ✅（`Theme.dark` ← `styleHints.colorScheme`） |
| exe 体积 | ≤ 50 MB | ⏳ 见第 7 节 |
| Linux | 能起来 | ✅（`QQuickStyle` 保留；无 DISPLAY 时自动 `offscreen` 兜底） |

### 自检矩阵（全部真跑）

| 脚本 | 覆盖 | 结果 |
|---|---|---|
| `_verify_integration.py` | bridge 构造 / 跨线程信号 / 重播 / 关闭落盘 / 画质传导 / 正则 / 6 页 QML 加载 | **50/50 PASS** |
| `_verify_playback_chain.py` | 真实网络：UGC 播放链 / PGC 番剧链 / 弹幕 / SponsorBlock / 画质上限 / 历史 | **17/17 PASS** |
| `_verify_settings.py` | 钳制边界 / QML→conf 整链路 / 离屏渲染 | **128/128 PASS** |
| `_verify_shell.py` | 自启注册表读写清理 / 托盘 / CloseDialog | **26/26 PASS** |
| `_verify_close_flow.py` | 点 X → 弹框 → 选择 → 落盘 → 动作（5 个场景） | **14/14 PASS** |
| `_verify_quality.py` | 画质修复（UGC 不回退 / PGC 可播 / max_qn / 脏数据） | **ALL PASS** |
| `_verify_entry.py` | 真实入口 main() 起来 + 主窗口截图 | **PASS** |
| `unittest discover -s legacy/tests` | 后端 193 项回归 | **193 tests OK** |

## 6.1 集成期间发现并修掉的真实 bug

这几个都是「单独看 QML 文件都正常、一跑真实入口就暴露」的问题：

1. **`engine.rootObjects()[0]` 拿错了窗口。**
   `CloseDialog.qml` 先加载，它成为 `rootObjects()[0]`；之后加载 `Main.qml` 时若仍取
   `[0]`，拿到的还是关闭询问框。结果 `win.show()` 把询问框弹出来了、主窗口不显示。
   修法：记下加载前的数量，取新增的最后一个；并断言 `title` 非空。

2. **`bridge` 被提前回收，退出时刷一屏 `Cannot read property 'paused' of null`。**
   `setContextProperty` 不接管所有权。`bridge` 若是 `main()` 里的局部变量，解释器退出时
   PySide 包装对象先于 QML 引擎销毁，所有 `bridge.xxx` 绑定在析构阶段读到 null。
   修法：`app._dsh_bridge = bridge` 保活到进程结束（`settings_bridge` 同理）。

3. **Python 调不到 QML 的 `function`。**
   托盘菜单原本直接 `tray.quitRequested.connect(win.requestQuit)`，报
   `'PySide6.QtQuick.QQuickWindow' object has no attribute 'requestQuit'` ——
   QML 里 `function foo()` 声明的东西不是 Python 可调用属性。
   修法：Python 侧只 emit `bridge` 的信号（`trayShowRequested` / `trayQuitRequested` /
   `minimizeToTrayRequested`），QML 侧 `Connections` 接住。CloseDialog 的 `accepted`
   同理，改在 `Main.qml` 的 `Connections` 里接。

4. **`QApplication.exec` 与 `QGuiApplication` 的坑。**
   托盘菜单是 `QWidget`，必须用 `QApplication`（`QGuiApplication` 下 `QMenu()` 直接崩在
   C++ 侧且无 Python 栈）。shell-agent 已把判断从 `instance() is None` 改成
   `isinstance(instance(), QApplication)`。

5. **离屏渲染会漏画 Fluent 控件。**
   `offscreen` QPA 下 `ComboBox` 截出来是空白（不是没渲染，是平台插件不画）。
   真实 `windows` QPA 下正常。所以设置页截图脚本在 Windows 上应设
   `QT_QPA_PLATFORM=windows`，仅 CI 无桌面时才用 offscreen。

6. **`import "."` 会让 Fluent 控件的 `implicitHeight` 塌成 0。**
   同目录本来就隐式可解析，加了这个 import 反而让 `TextField`/`ComboBox` 高度变 0、
   完全不可见且不报错。settings-agent 踩到并写进注释。

7. **QML 传 dict 到 Python 是 `QJSValue` 不是 `dict`。**
   `isinstance(data, dict)` 恒为 False → 所有字段被静默丢弃，表现为「点保存没反应也不报错」。
   `settings_bridge.py` 加了 `_as_dict()` 走 `toVariant()`。

## 7. 已知遗留

1. **exe 体积未实测**。`build_qml.spec` 的手动 binaries 过滤按
   `ui-kit/README.md` 实测数据写成（不裁 150 MB / 全裁 ≈48.8 MB），但本机未跑
   `pyinstaller` 完整构建。首次构建请核对 `dist/BiliYTPlayer.exe` 大小，
   若 > 50 MB 说明 `_DROP_FRAGMENTS` 漏了某个模态（用 `pyi-archive_viewer` 查大头）。
2. **托盘图标只验证了「不崩 + 3 项菜单 + 16/32 尺寸」**。
   离屏平台下 `QSystemTrayIcon.isSystemTrayAvailable()` 返回 `False`，真机任务栏
   出现图标这条未实测。
3. **mpv 真实起窗未实测**：播放链路已用记录器替换 `launch_player` 验证到底
   （直链/标题/音轨/弹幕/SponsorBlock/画质上限全部正确），但「mpv 窗口真的播起来」
   与 `launch_player` 的参数构造仍需实机跑一次（参数与原版逐字一致）。
4. `legacy/bili_yt_player.pyw` 保留未删，可作回退；后续可删（约 500 行纯 UI）。
5. 设置页没把 legacy 的 `behavior`(skip/mute) / `server` / `timeout` / `report_views` /
   `debug` / `speedup_gap` / `cache_limit` / `scale_xml_size` 这些边角配置项搬进 UI。
   它们仍可通过手改 conf 生效。
6. 开发期临时探针在 `_scratch/`（已 gitignore）；正式自检脚本保留在仓库根：
   `_verify_quality.py` / `_verify_shell.py` / `_verify_settings.py` /
   `_verify_integration.py` / `_verify_playback_chain.py` / `_verify_close_flow.py` /
   `_verify_entry.py`。
7. EUIKit 的 `ESpringListDelegate` 原本只有 `doubleClicked`，为了「单击选中 + 双击重播」
   补了一个 `clicked` 信号（2 行）。这是对组件包的唯一改动，`ui-kit/` 下的原件未动。


## 8. 开发期工具

```bash
# 离屏/真实渲染截图（中文字体必须指到系统字体目录）
python _shot.py <qml> <out.png> [宽] [高] [light|dark]
python _shot_main.py <out.png> [light|dark]      # 带 mock bridge 的主窗口

# 自检（全部可独立跑）
python _verify_integration.py     # 桥接 / 配置 / 6 页加载（50 项）
python _verify_playback_chain.py  # 真实网络播放链（17 项）
python _verify_close_flow.py      # 点 X 全流程（14 项）
python _verify_settings.py        # 设置页钳制与落盘（128 项）
python _verify_shell.py           # 自启 / 托盘 / 关闭框（26 项，含注册表清理）
python _verify_quality.py         # 画质修复（真实联网）
python _verify_entry.py           # 真实入口启动 + 截图

# 后端回归（不可省）
python -m unittest discover -s legacy/tests -t .
```

> `_shot.py` 的关键点：`QT_QPA_FONTDIR=C:\Windows\Fonts`。Qt 6 不再自带字体，
> 不设这个环境变量时所有中文渲染成方块（`QFontDatabase: Cannot find font directory`）。
>
> 另一个关键点：Windows 上要 `QT_QPA_PLATFORM=windows`。`offscreen` 平台插件不画
> `ComboBox` 等 Fluent 控件（截出来是空白），会被误判成布局 bug。

