import QtQuick
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "nb11b.adaptive-audio"
  ipcTarget: "nb11b.adaptive-audio"
  manageIpc: false
  property var anchorItem: null
  property var hostWidget: null
  property var audioStatus: ({ state: "waiting", enabled: true })
  readonly property var barIdentity: hostWidget || root

  function open() { root.controller.show() }
  function close() { root.controller.hide() }
  function toggle() { if (root.opened) root.close(); else root.open() }
  function closeForPopoutSwitch() { root.close() }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(320))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight)
    content: PanelKeyCatcher {
      anchors.fill: parent
      implicitHeight: contentColumn.implicitHeight
      onCloseRequested: root.close()
      Column {
        id: contentColumn
        width: parent.width
        spacing: Style.space(8)
        Text { textFormat: Text.PlainText; text: "Adaptive Audio"; color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "State: " + root.audioStatus.state; color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "Output: " + (root.audioStatus.source || "none"); color: root.bar ? root.bar.foreground : Color.foreground; elide: Text.ElideRight; width: parent.width }
        Text { textFormat: Text.PlainText; text: "Target: 192.168.254.75:4000"; color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "Packets/s: " + (root.audioStatus.packet_rate || 0); color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "Receiver age: " + (root.audioStatus.receiver_age_s === null || root.audioStatus.receiver_age_s === undefined ? "waiting" : root.audioStatus.receiver_age_s + " s"); color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "Crossover: " + (root.audioStatus.crossover_low_hz || "—") + " / " + (root.audioStatus.crossover_high_hz || "—") + " Hz"; color: root.bar ? root.bar.foreground : Color.foreground }
        Text { textFormat: Text.PlainText; text: "Drops / underruns: " + (root.audioStatus.drops || 0) + " / " + (root.audioStatus.underruns || 0); color: root.bar ? root.bar.foreground : Color.foreground }
        Text {
          textFormat: Text.PlainText
          text: root.audioStatus.enabled === false ? "Turn streaming on" : "Turn streaming off"
          color: root.bar ? root.bar.foreground : Color.foreground
          font.bold: true
          MouseArea { anchors.fill: parent; onClicked: if (root.hostWidget) root.hostWidget.toggleAudio() }
        }
      }
    }
  }
}
