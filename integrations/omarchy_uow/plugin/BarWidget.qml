import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "nb11b.adaptive-audio"

  readonly property string cli: Quickshell.env("HOME") + "/.local/bin/omarchy-audio-worker"
  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") + "/omarchy-uow-audio"
  readonly property string stateDir: Quickshell.env("HOME") + "/.local/state/omarchy-uow-audio"
  property var audioStatus: ({ state: "waiting", enabled: true })
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function toggleAudio() {
    if (audioStatus.enabled === false) { if (!onProcess.running) onProcess.running = true }
    else { if (!offProcess.running) offProcess.running = true }
  }
  function acceptStatus(raw) {
    try {
      if (raw.length > 4096) return
      var value = JSON.parse(raw)
      var allowed = ["waiting", "off", "preflight", "streaming", "receiver-wait", "denied", "no-monitor", "capture-error", "error"]
      if (!value || allowed.indexOf(value.state) < 0 || typeof value.enabled !== "boolean") return
      if (value.source !== null && value.source !== undefined && (typeof value.source !== "string" || value.source.length > 160)) return
      root.audioStatus = value
    } catch (e) { root.audioStatus = ({ state: "error", enabled: true }) }
  }
  function injectPanel() {
    var panel = panelLoader.item
    if (!panel) return
    panel.bar = root.bar
    panel.settings = root.settings
    panel.anchorItem = button
    panel.hostWidget = root
    panel.audioStatus = root.audioStatus
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onAudioStatusChanged: if (panelLoader.item) panelLoader.item.audioStatus = root.audioStatus
  Component.onCompleted: workerProcess.running = true

  Process {
    id: workerProcess
    command: [root.cli, "serve", "--gateway", root.runtimeDir + "/gateway.sock", "--operator-token", root.stateDir + "/operator.token", "--worker-token", root.stateDir + "/worker.token"]
  }
  Process {
    id: heartbeatProcess
    command: [root.cli, "heartbeat"]
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.acceptStatus(text) }
  }
  Process { id: onProcess; command: [root.cli, "on"] }
  Process { id: offProcess; command: [root.cli, "off"] }
  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: {
      if (!workerProcess.running) workerProcess.running = true
      if (!heartbeatProcess.running) heartbeatProcess.running = true
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel) }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.audioStatus.state === "streaming" ? "♫" : root.audioStatus.state === "off" ? "◼" : "♪"
    slotSize: Style.bar.statusSlot
    tooltipText: "Adaptive Audio: " + root.audioStatus.state
    onPressed: function(b) { root.toggle() }
  }
}
