import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Omarchy-panel layout for z13-power, same shape as battery / network /
// display: hero, two-column stats, section header, bordered profile pills,
// then a labeled toggle. Right-click on the tray bolt opens this instead
// of the generic dbusmenu list.
Column {
  id: root
  width: parent ? parent.width : implicitWidth
  spacing: Style.space(14)

  property var bar: null
  property color foreground: bar ? bar.foreground : Color.foreground
  property color accent: Color.accent
  property string fontFamily: bar ? bar.fontFamily : Style.font.family
  property var run: bar && typeof bar.run === "function" ? bar.run : function() {}
  // When true, hide the Power hero/stats — the host panel (omarchy.power)
  // already shows battery. Only pills + Automatic + Lock + fill + actions remain.
  property bool embedInPowerPanel: false

  property var status: ({
    mode: "performance",
    label: "Performance",
    automatic: true,
    locked: false,
    ac: true,
    capacity: null,
    tdp: null,
    profile: "",
    fill_once: false,
    charge_limit: null
  })

  // QML/JS only accepts \\uXXXX (4 hex digits). Nerd Font glyphs live
  // above U+FFFF, so they have to be built from a codepoint.
  function glyph(cp) { return String.fromCodePoint(cp) }

  readonly property var modes: [
    { id: "max", label: "Max", icon: glyph(0xF0E7) },
    { id: "performance", label: "Perf", icon: glyph(0xF04C5) },
    { id: "balanced", label: "Mid", icon: glyph(0xF04BA) },
    { id: "silent", label: "Quiet", icon: glyph(0xF0594) },
    { id: "lowpower", label: "Low", icon: glyph(0xF0331) }
  ]
  readonly property string settingsGlyph: glyph(0xF0493)
  readonly property string diagnoseGlyph: glyph(0xF0D7A)

  readonly property string activeMode: String(status.mode || "performance")
  readonly property bool automatic: status.automatic === true
  readonly property bool locked: status.locked === true
  readonly property bool fillOnce: status.fill_once === true
  property var confChargeLimit: null
  readonly property var chargeLimit: {
    if (root.confChargeLimit !== null && root.confChargeLimit !== undefined)
      return root.confChargeLimit
    var n = status.charge_limit
    if (n === undefined || n === null || n === "")
      return null
    var v = Number(n)
    return isFinite(v) ? v : null
  }
  readonly property bool onAc: status.ac === true
  readonly property var capacity: status.capacity
  readonly property string tdpLabel: status.tdp !== undefined && status.tdp !== null && status.tdp !== ""
    ? String(status.tdp) + "W" : "—"
  readonly property string heroMeta: automatic ? "Automatic" : (locked ? "Locked" : "Manual")
  readonly property string sourceValue: onAc ? "AC" : (capacity !== null && capacity !== undefined ? "Battery" : "—")
  readonly property string batteryValue: capacity !== null && capacity !== undefined ? String(capacity) + "%" : "—"

  property bool diagnoseOpen: false
  property string diagnoseText: ""
  property bool diagnoseBusy: false

  function binCommand(name, args) {
    // ~/.local/bin (from-source), then /usr/bin (package), then PATH.
    // Omarchy's shell PATH often skips ~/.local/bin.
    var rest = args ? args : []
    return [
      "bash", "-c",
      'for p in "$HOME/.local/bin/$1" "/usr/bin/$1"; do [ -x "$p" ] && exec "$p" "${@:2}"; done; exec "$1" "${@:2}"',
      "z13-bin",
      name
    ].concat(rest)
  }

  function send(op, extra) {
    var payload = extra ? extra : {}
    payload.op = op
    // Write the command file directly. The packaged /usr/bin/z13-power
    // may not have `cmd` yet, and the shell's PATH often skips ~/.local/bin.
    cmdProc.command = [
      "bash", "-c",
      "mkdir -p \"$HOME/.local/state/z13-power\" && printf '%s\\n' \"$1\" > \"$HOME/.local/state/z13-power/command.json.tmp\" && mv -f \"$HOME/.local/state/z13-power/command.json.tmp\" \"$HOME/.local/state/z13-power/command.json\"",
      "z13-cmd",
      JSON.stringify(payload)
    ]
    cmdProc.running = true
  }

  function setMode(mode) {
    send("mode", { mode: mode })
  }

  function toggleAutomatic() {
    if (automatic) {
      send("mode", { mode: activeMode })
    } else {
      send("automatic")
    }
  }

  function toggleLock() {
    send("lock", { locked: !locked })
  }

  function toggleFillOnce() {
    send("fill", { fill: !fillOnce })
  }

  function parseChargeLimit(text) {
    var m = String(text || "").match(/charge_limit\s*=\s*(\d+)/)
    if (!m)
      return null
    var n = Number(m[1])
    return isFinite(n) ? n : null
  }

  function toggleDiagnose() {
    if (root.diagnoseOpen) {
      root.diagnoseOpen = false
      root.diagnoseBusy = false
      diagnoseProc.running = false
      return
    }
    if (root.diagnoseBusy) return
    root.diagnoseBusy = true
    root.diagnoseText = ""
    diagnoseProc.command = binCommand("z13-power", ["diagnose"])
    diagnoseProc.running = false
    diagnoseProc.running = true
  }

  FileView {
    id: statusFile
    path: Quickshell.env("HOME") + "/.local/state/z13-power/status.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        root.status = JSON.parse(text())
      } catch (e) {}
    }
  }

  FileView {
    id: batteryFile
    path: Quickshell.env("HOME") + "/.config/z13-power/battery.conf"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.confChargeLimit = root.parseChargeLimit(text())
  }

  Timer {
    interval: 1000
    running: root.visible
    repeat: true
    onTriggered: {
      statusFile.reload()
      batteryFile.reload()
    }
  }

  Component.onCompleted: {
    statusFile.reload()
    batteryFile.reload()
  }
  onVisibleChanged: if (visible) {
    statusFile.reload()
    batteryFile.reload()
  }

  Process {
    id: cmdProc
  }

  Process {
    id: diagnoseProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.diagnoseText = String(text || "").trim()
        root.diagnoseBusy = false
        root.diagnoseOpen = true
      }
    }
    onExited: function() {
      root.diagnoseBusy = false
    }
  }

  // ---------- Hero ----------
  Item {
    visible: !root.embedInPowerPanel
    width: parent.width
    implicitHeight: visible ? Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroTdp.implicitHeight) : 0

    Text {
      id: heroIcon
      text: "\uf0e7"
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.display
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Column {
      id: heroLabels
      anchors.left: heroIcon.right
      anchors.leftMargin: Style.space(14)
      anchors.right: heroTdp.left
      anchors.rightMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      Text {
        text: "Power"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        font.bold: true
        elide: Text.ElideRight
        width: parent.width
      }

      Text {
        text: root.heroMeta.toUpperCase()
        color: Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        font.letterSpacing: 1.2
        elide: Text.ElideRight
        width: parent.width
      }
    }

    Text {
      id: heroTdp
      text: root.tdpLabel
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.displayLarge
      font.bold: true
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  // ---------- Stats ----------
  Row {
    visible: !root.embedInPowerPanel
    width: parent.width
    spacing: Style.space(20)

    Column {
      width: (parent.width - parent.spacing) / 2
      spacing: Style.spacing.labelGap
      InfoPair { label: "Source"; value: root.sourceValue }
      InfoPair { label: "Battery"; value: root.batteryValue }
    }

    Column {
      width: (parent.width - parent.spacing) / 2
      spacing: Style.spacing.labelGap
      InfoPair { label: "Mode"; value: String(root.status.label || root.activeMode) }
      InfoPair { label: "Firmware"; value: String(root.status.profile || "—") }
    }
  }

  PanelSeparator {
    visible: !root.embedInPowerPanel
    foreground: root.foreground
  }

  // ---------- Profile picker ----------
  Column {
    width: parent.width
    spacing: Style.space(10)

    Item {
      width: parent.width
      implicitHeight: Math.max(profileHeader.implicitHeight, autoRow.implicitHeight)

      PanelSectionHeader {
        id: profileHeader
        text: "POWER PROFILE"
        foreground: root.foreground
        fontFamily: root.fontFamily
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
      }

      Row {
        id: autoRow
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(6)

        PanelSectionHeader {
          id: autoLabel
          text: "AUTOMATIC"
          foreground: root.foreground
          fontFamily: root.fontFamily
          anchors.verticalCenter: parent.verticalCenter
        }

        ToggleSwitch {
          id: autoSwitch
          trackHeight: Math.round(autoLabel.font.pixelSize * 1.2)
          cursorPad: Style.space(3)
          anchors.verticalCenter: autoLabel.verticalCenter
          anchors.verticalCenterOffset: Math.round(autoLabel.topPadding / 2)
          checked: root.automatic
          foreground: root.foreground
          accent: root.accent
          onToggled: root.toggleAutomatic()
        }
      }
    }

    Row {
      id: profileRow
      width: parent.width
      spacing: Style.space(6)

      readonly property real cellWidth: root.modes.length > 0
        ? (width - spacing * (root.modes.length - 1)) / root.modes.length
        : 0

      Repeater {
        model: root.modes

        Button {
          required property var modelData
          width: profileRow.cellWidth
          iconText: modelData.icon
          iconSize: Style.font.title
          text: modelData.label
          fontSize: Style.font.bodySmall
          foreground: root.foreground
          accent: root.accent
          fontFamily: root.fontFamily
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY + Style.space(2)
          bordered: true
          active: root.activeMode === modelData.id
          selected: root.activeMode === modelData.id
          onClicked: root.setMode(modelData.id)
        }
      }
    }
  }

  PanelSeparator { foreground: root.foreground }

  Toggle {
    width: parent.width
    label: "Lock profile"
    description: root.automatic
      ? "Pick a profile first"
      : "Keep this mode when you plug in or unplug"
    checked: root.locked
    foreground: root.foreground
    accent: root.accent
    fontFamily: root.fontFamily
    opacity: root.automatic ? 0.45 : 1
    onClicked: if (!root.automatic) root.toggleLock()
  }

  Toggle {
    width: parent.width
    label: "Charge to 100%"
    description: root.fillOnce
      ? (root.chargeLimit !== null
          ? "This plug-in only · returns to " + root.chargeLimit + "%"
          : "This plug-in only · then the cap comes back")
      : (root.chargeLimit !== null && root.chargeLimit < 100
          ? "Lift the " + root.chargeLimit + "% cap for this plug-in"
          : "Fill all the way this plug-in, then the cap returns")
    checked: root.fillOnce
    foreground: root.foreground
    accent: root.accent
    fontFamily: root.fontFamily
    onClicked: root.toggleFillOnce()
  }

  Row {
    width: parent.width
    spacing: Style.space(6)

    Button {
      width: (parent.width - parent.spacing) / 2
      text: "Settings"
      iconText: root.settingsGlyph
      foreground: root.foreground
      accent: root.accent
      fontFamily: root.fontFamily
      bordered: true
      onClicked: {
        cmdProc.command = binCommand("z13-power-settings")
        cmdProc.running = false
        cmdProc.running = true
      }
    }

    Button {
      width: (parent.width - parent.spacing) / 2
      text: root.diagnoseBusy ? "Checking…" : "Diagnose"
      iconText: root.diagnoseGlyph
      foreground: root.foreground
      accent: root.accent
      fontFamily: root.fontFamily
      bordered: true
      active: root.diagnoseOpen
      onClicked: root.toggleDiagnose()
    }
  }

  Text {
    visible: root.diagnoseOpen && root.diagnoseText !== ""
    width: parent.width
    text: root.diagnoseText
    color: Qt.darker(root.foreground, 1.2)
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  component InfoPair: Item {
    property string label: ""
    property string value: ""

    width: parent.width
    implicitHeight: Math.max(labelText.implicitHeight, valueText.implicitHeight)

    Text {
      id: labelText
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      text: label
      color: root.foreground
      opacity: 0.6
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }

    Text {
      id: valueText
      anchors.right: parent.right
      anchors.left: labelText.right
      anchors.leftMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      horizontalAlignment: Text.AlignRight
      text: value
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
    }
  }
}
