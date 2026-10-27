import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../euikit"

// 通用 —— 关闭行为 / 关闭询问 / 开机自启
// 映射 general.conf：close_action / ask_on_close / autostart_mode
SettingsPage {
    id: page

    title: "通用"
    subtitle: "点窗口 × 之后的行为与启动方式。保存后立即生效。"

    function load() {
        if (!page.bridge) return
        var d = page.bridge.pageData("general")
        page.cfg = d ? d : {}
        closeGroup.sync()
    }

    Component.onCompleted: load()

    // ------------------------------------------------------------ 关闭行为
    ESpringCard {
        Layout.fillWidth: true
        cardColor: Theme.card
        borderColor: Theme.stroke

        Text {
            Layout.fillWidth: true
            text: "点击 × 之后"
            color: Theme.text
            font.pixelSize: Theme.bodySize
            font.weight: Font.DemiBold
        }

        ButtonGroup {
            id: closeGroup

            function chosen() {
                if (closeRadio.checked) return "close"
                if (trayRadio.checked) return "tray"
                return "close"
            }

            // 把 conf 值同步到单选状态（"ask" 老默认值显示成"关闭程序"）
            function sync() {
                trayRadio.checked = page.cfg.close_action === "tray"
                closeRadio.checked = !trayRadio.checked
            }
        }

        RadioButton {
            id: closeRadio
            objectName: "closeActionClose"
            text: "关闭程序"
            checked: page.cfg.close_action !== "tray"
            ButtonGroup.group: closeGroup
        }

        RadioButton {
            id: trayRadio
            objectName: "closeActionTray"
            text: "最小化到托盘（后台继续监听剪贴板）"
            ButtonGroup.group: closeGroup
        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: 2
            visible: page.cfg.close_action === "ask"
            text: "当前配置是「每次都询问」；选定一项并保存后才会固定行为。"
            color: Theme.text3
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: 4
            Layout.bottomMargin: 4
            color: Theme.stroke
        }

        CheckBox {
            id: askBox
            objectName: "askOnClose"
            text: "关闭时询问我"
            checked: page.cfg.ask_on_close !== false
        }

        Text {
            Layout.fillWidth: true
            text: "取消勾选 = 下次关窗直接执行上面的选择，不再弹询问框。"
            color: Theme.text3
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }

    // ------------------------------------------------------------ 开机自启
    ESpringCard {
        Layout.fillWidth: true
        cardColor: Theme.card
        borderColor: Theme.stroke

        Text {
            Layout.fillWidth: true
            text: "开机自启"
            color: Theme.text
            font.pixelSize: Theme.bodySize
            font.weight: Font.DemiBold
        }

        SettingRow {
            Layout.fillWidth: true
            label: "启动方式"
            hint: "写入 HKCU\\...\\CurrentVersion\\Run"

            ComboBox {
                id: autoCombo
                objectName: "autostartCombo"
                Layout.preferredWidth: 260
                textRole: "label"
                valueRole: "key"
                model: page.meta && page.meta.autostart ? page.meta.autostart : []
                currentIndex: {
                    var want = page.cfg.autostart_mode || "none"
                    for (var i = 0; i < model.length; i++)
                        if (model[i].key === want) return i
                    return 0
                }
                // ComboBox 自带的 currentValue 就是 valueRole 取到的 key
                function mode() { return currentValue !== undefined ? currentValue : "none" }
            }
        }

        Text {
            Layout.fillWidth: true
            text: page.cfg.autostart_enabled
                  ? "注册表项已写入，当前已生效。"
                  : "仅打包成 exe 后可用：源码运行时取不到程序路径，保存时会给出提示。"
            color: page.cfg.autostart_enabled ? Theme.ok : Theme.text3
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }

    // 保存入口（PageActions 与自检脚本都走这里）
    function save() {
        if (!page.bridge) return
        page.report(page.bridge.saveGeneral({
            close_action: closeGroup.chosen(),
            ask_on_close: askBox.checked,
            autostart_mode: autoCombo.mode()
        }))
    }

    PageActions {
        Layout.fillWidth: true
        primaryText: "保存"
        status: page.statusText
        statusOk: page.statusOk
        onPrimaryClicked: page.save()
    }
}
