import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    width: 720
    height: 520
    minimumWidth: 590
    minimumHeight: 460
    title: qsTr("Adaptive Audio")
    color: "#17191e"
    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    function hz(value) { return value > 0 ? Qt.locale().toString(value, 'f', value % 1 === 0 ? 0 : 1) + " Hz" : qsTr("Unavailable") }
    function stateText() {
        if (backend.state === "streaming") return qsTr("Streaming")
        if (backend.state === "off") return qsTr("Off")
        if (backend.state === "receiver-wait" || backend.state === "preflight") return qsTr("Waiting for receiver")
        if (backend.state === "unavailable") return qsTr("Bar plugin is off or worker unavailable")
        return backend.state
    }
    function changeText() {
        if (backend.changeState === "receiver-reported") return qsTr("Receiver reports the requested settings")
        if (backend.changeState === "pending") return qsTr("Sent; waiting for receiver report")
        if (backend.changeState === "unconfirmed") return qsTr("Sent; receiver confirmation missing")
        if (backend.changeState === "denied") return qsTr("Change denied by local authority")
        if (backend.changeState === "interrupted") return qsTr("Change interrupted")
        return ""
    }

    Shortcut { sequence: "Q"; context: Qt.ApplicationShortcut; onActivated: root.close() }
    Shortcut { sequence: "Space"; context: Qt.ApplicationShortcut; onActivated: backend.setStreaming(!backend.enabled) }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("Adaptive Audio"); font.pixelSize: 23; font.bold: true; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Label { text: root.stateText(); textFormat: Text.PlainText; color: backend.state === "streaming" ? "#a7e0b3" : "#ffcc9e" }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: statusColumn.implicitHeight + 26
            color: "#252932"
            radius: Math.min(6, theme.radius)
            ColumnLayout {
                id: statusColumn
                anchors.fill: parent
                anchors.margins: 13
                spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Playback output"); color: "#b9c1cf" }
                    Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft; text: backend.source || qsTr("No output captured"); textFormat: Text.PlainText }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Receiver"); color: "#b9c1cf" }
                    Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; text: backend.receiverAge >= 0 ? qsTr("Reported %1 s ago").arg(backend.receiverAge.toFixed(1)) : qsTr("No recent report"); textFormat: Text.PlainText }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("Stream laptop playback to ESP32"); textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Switch { checked: backend.enabled; enabled: backend.state !== "unavailable"; onClicked: backend.setStreaming(checked) }
        }

        Label { text: qsTr("Crossover"); font.pixelSize: 18; font.bold: true; textFormat: Text.PlainText }
        Label {
            Layout.fillWidth: true
            text: qsTr("Receiver reports: %1  /  %2").arg(root.hz(backend.currentLow)).arg(root.hz(backend.currentHigh))
            textFormat: Text.PlainText
            color: "#b9c1cf"
        }

        Rectangle {
            id: bandTrack
            Layout.fillWidth: true
            implicitHeight: 88
            color: "#252932"
            radius: Math.min(6, theme.radius)
            property real lowRatio: backend.editLow > 0 ? Math.max(0, Math.min(1, Math.log(backend.editLow / 20) / Math.log(1000))) : 0.33
            property real highRatio: backend.editHigh > 0 ? Math.max(0, Math.min(1, Math.log(backend.editHigh / 20) / Math.log(1000))) : 0.66
            property int activeMarker: 0
            function frequencyAt(x) { return Math.round(20 * Math.pow(1000, Math.max(0, Math.min(1, x / inner.width)))) }
            Item {
                id: inner
                anchors.fill: parent
                anchors.margins: 13
                Rectangle { x: 0; width: inner.width * bandTrack.lowRatio; height: inner.height; color: "#28455b"; radius: 2; Label { anchors.centerIn: parent; text: qsTr("Low"); color: "white" } }
                Rectangle { x: inner.width * bandTrack.lowRatio; width: Math.max(0, inner.width * (bandTrack.highRatio - bandTrack.lowRatio)); height: inner.height; color: "#315844"; radius: 2; Label { anchors.centerIn: parent; text: qsTr("Mid"); color: "white" } }
                Rectangle { x: inner.width * bandTrack.highRatio; width: inner.width * (1 - bandTrack.highRatio); height: inner.height; color: "#604a32"; radius: 2; Label { anchors.centerIn: parent; text: qsTr("High"); color: "white" } }
                Rectangle { visible: backend.currentLow > 0; x: inner.width * bandTrack.lowRatio - 2; width: 4; height: inner.height; color: theme.accent }
                Rectangle { visible: backend.currentHigh > 0; x: inner.width * bandTrack.highRatio - 2; width: 4; height: inner.height; color: theme.accent }
                MouseArea {
                    anchors.fill: parent
                    enabled: backend.receiverAge >= 0 && backend.receiverAge <= 3 && backend.currentLow > 0
                    cursorShape: Qt.SizeHorCursor
                    onPressed: function(mouse) {
                        bandTrack.activeMarker = Math.abs(mouse.x - inner.width * bandTrack.lowRatio) < Math.abs(mouse.x - inner.width * bandTrack.highRatio) ? 1 : 2
                        updateMarker(mouse.x)
                    }
                    onPositionChanged: function(mouse) { if (pressed) updateMarker(mouse.x) }
                    onReleased: bandTrack.activeMarker = 0
                    function updateMarker(x) {
                        const hz = bandTrack.frequencyAt(x)
                        if (bandTrack.activeMarker === 1) backend.editLow = Math.min(hz, backend.editHigh - 1)
                        if (bandTrack.activeMarker === 2) backend.editHigh = Math.max(hz, backend.editLow + 1)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                Layout.fillWidth: true
                Label { text: qsTr("Low / Mid split (Hz)"); textFormat: Text.PlainText }
                SpinBox {
                    id: lowSpin
                    Layout.fillWidth: true
                    visible: backend.currentLow > 0
                    enabled: backend.receiverAge >= 0 && backend.receiverAge <= 3
                    from: 1; to: 23998; stepSize: 1
                    editable: true
                    value: Math.max(1, Math.round(backend.editLow))
                    onValueModified: backend.editLow = value
                }
                Label { visible: !lowSpin.visible; text: qsTr("Unavailable"); color: "#b9c1cf" }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Label { text: qsTr("Mid / High split (Hz)"); textFormat: Text.PlainText }
                SpinBox {
                    id: highSpin
                    Layout.fillWidth: true
                    visible: backend.currentHigh > 0
                    enabled: backend.receiverAge >= 0 && backend.receiverAge <= 3
                    from: 2; to: 23999; stepSize: 1
                    editable: true
                    value: Math.max(2, Math.round(backend.editHigh))
                    onValueModified: backend.editHigh = value
                }
                Label { visible: !highSpin.visible; text: qsTr("Unavailable"); color: "#b9c1cf" }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Button { text: qsTr("Apply"); enabled: backend.canApply; onClicked: backend.apply() }
            Button { text: qsTr("Revert edits"); onClicked: backend.revertEdits() }
            Item { Layout.fillWidth: true }
            Label { text: root.changeText(); color: backend.changeState === "receiver-reported" ? "#a7e0b3" : "#ffcc9e"; textFormat: Text.PlainText }
        }
        Item { Layout.fillHeight: true }
    }
}
