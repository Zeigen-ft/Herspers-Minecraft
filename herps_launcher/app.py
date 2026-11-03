"""Qt desktop UI. Long operations run in workers; the window stays responsive."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QUrl, QLockFile
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget)

from .core import Launcher, GAME, REVISION, build_native, pairs, read_json, tailscale, server_address
from . import __version__

STYLE = """
QWidget { background: #10151d; color: #dde7ee; font-family: 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 14px; }
QMainWindow { background: #10151d; }
QLabel#brand { color: #a4f0b3; font-size: 23px; font-weight: 800; padding: 18px 4px; }
QLabel#heading { font-size: 30px; font-weight: 700; padding-bottom: 12px; }
QLabel#muted { color: #9eafc1; }
QLabel#hero { background: #1c302d; border: 1px solid #325b49; border-radius: 16px; padding: 28px; font-size: 23px; }
QPushButton { background: #23303e; border: 1px solid #354658; border-radius: 8px; padding: 11px 16px; text-align: left; }
QPushButton:hover { background: #304656; border-color: #7cbe99; }
QPushButton:disabled { color: #7b8895; background: #202731; }
QPushButton#play { background: #91edab; color: #10271b; font-size: 24px; font-weight: 800; padding: 22px; }
QPushButton#nav { border: none; background: transparent; padding: 14px; }
QPushButton#nav:checked { background: #263b35; color: #a4f0b3; }
QLineEdit, QComboBox, QSpinBox, QListWidget, QTextEdit { background: #19222e; border: 1px solid #344252; border-radius: 7px; padding: 9px; selection-background-color: #31574a; }
QListWidget::item { padding: 12px; border-bottom: 1px solid #293544; }
QListWidget::item:selected { background: #2a4b3d; }
QCheckBox { padding: 8px; }
QStatusBar { color: #a4b7c8; background: #18202a; }
"""


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)
    line = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.done.emit(self.function(self.line.emit))
        except Exception as error:
            self.failed.emit(str(error))


class Window(QMainWindow):
    def __init__(self, launcher=None):
        super().__init__()
        self.launcher = launcher or Launcher()
        self.worker = None
        self.mod_entries = []
        self.server_entries = []
        self.setWindowTitle(f"Herps Launcher · {__version__}")
        self.resize(1130, 790)
        self.setMinimumSize(900, 640)
        shell = QWidget()
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(20, 18, 26, 18)
        layout.setSpacing(28)
        sidebar = QVBoxLayout()
        brand = QLabel("HERPS\nLAUNCHER")
        brand.setObjectName("brand")
        sidebar.addWidget(brand)
        self.pages = QStackedWidget()
        self.nav = []
        for index, name in enumerate(("Home", "Mods", "Shaders", "Multiplayer", "Settings")):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.navigate(i))
            sidebar.addWidget(button)
            self.nav.append(button)
        sidebar.addStretch()
        badge = QLabel("JAVA EDITION\n26.3 · Horizon 0.7.6\n\nWindows / macOS")
        badge.setObjectName("muted")
        sidebar.addWidget(badge)
        side = QWidget()
        side.setLayout(sidebar)
        side.setFixedWidth(195)
        layout.addWidget(side)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)
        self.home_page()
        self.mods_page()
        self.shaders_page()
        self.multiplayer_page()
        self.settings_page()
        self.navigate(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(800)
        self.refresh()
        self.statusBar().showMessage("Select your Herspers Java installation in Settings to get started.")

    def page(self, title, description):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("heading")
        box.addWidget(heading)
        label = QLabel(description)
        label.setWordWrap(True)
        label.setObjectName("muted")
        box.addWidget(label)
        self.pages.addWidget(page)
        return box

    def button(self, layout, label, function):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.guard(function))
        layout.addWidget(button)
        return button

    def guard(self, function):
        try:
            function()
        except Exception as error:
            QMessageBox.warning(self, "Herps Launcher", str(error))

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)

    def busy(self):
        return self.worker is not None or self.launcher.child is not None

    def require_idle(self):
        if self.busy():
            raise ValueError("Wait for the current operation or game to finish before changing the profile")

    def start_work(self, function, done=None):
        self.require_idle()
        self.worker = Worker(function, self)
        self.worker.line.connect(self.build_log.append)
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, "Operation failed", message))
        self.worker.done.connect(lambda result: done(result) if done else None)
        self.worker.finished.connect(self.work_finished)
        self.worker.start()
        self.play.setEnabled(False)

    def work_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.refresh()

    def home_page(self):
        box = self.page("Your next world awaits", "Manage your Herspers Java game, then jump back in.")
        self.hero = QLabel("Herspers Minecraft\nJava Edition 26.3")
        self.hero.setObjectName("hero")
        box.addWidget(self.hero)
        row = QHBoxLayout()
        row.addWidget(QLabel("PROFILE"))
        self.profile = QComboBox()
        self.profile.addItems(self.launcher.config["profiles"])
        self.profile.setCurrentText(self.launcher.config["profile"])
        self.profile.currentTextChanged.connect(lambda value: self.guard(lambda: self.change_profile(value)))
        row.addWidget(self.profile, 1)
        self.button(row, "+ New profile", self.new_profile)
        box.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        box.addWidget(self.summary)
        self.home_tail = QLabel("Tailscale · status not checked")
        self.home_tail.setObjectName("muted")
        box.addWidget(self.home_tail)
        self.play = self.button(box, "PLAY  →", self.play_game)
        self.play.setObjectName("play")
        self.button(box, "Clean startup · isolated game folder, no mods or shader", lambda: self.play_game(clean=True))
        box.addWidget(QLabel("RECENT ACTIVITY"))
        self.activity = QListWidget()
        box.addWidget(self.activity, 1)
        self.button(box, "Open launcher and game logs", lambda: self.open_path(self.launcher.state))

    def change_profile(self, value):
        if self.busy():
            self.profile.blockSignals(True)
            self.profile.setCurrentText(self.launcher.config["profile"])
            self.profile.blockSignals(False)
            raise ValueError("Profile changes are locked while the game or a build is running")
        self.launcher.config["profile"] = value
        self.launcher.save()
        self.refresh()

    def new_profile(self):
        self.require_idle()
        name, ok = QInputDialog.getText(self, "New profile", "Profile id (lowercase letters, numbers, underscores):")
        if ok:
            self.launcher.add_profile(name)
            self.profile.addItem(name)
            self.profile.setCurrentText(name)

    def play_game(self, clean=False, server="", name=""):
        self.start_work(lambda progress: self.launcher.launch(server, name, clean))
        self.statusBar().showMessage("Checking resources and starting the game…")

    def mods_page(self):
        box = self.page("Mods", "Horizon .hmod runtime/content mods and exact-revision .hnmod native sources. Forge and Fabric JARs are incompatible.")
        self.mod_list = QListWidget()
        self.mod_list.currentRowChanged.connect(self.mod_details)
        box.addWidget(self.mod_list, 1)
        self.mod_detail = QLabel("Select a mod to inspect its API and capabilities before enabling it.")
        self.mod_detail.setWordWrap(True)
        box.addWidget(self.mod_detail)
        row = QHBoxLayout()
        self.button(row, "Import mod…", self.import_mod)
        self.button(row, "Enable / disable", self.toggle_mod)
        self.button(row, "Remove to backup", self.remove_mod)
        box.addLayout(row)
        self.button(box, "Rebuild native mods…", self.rebuild)
        self.button(box, "Roll back · disable all native mods", self.rollback)
        self.build_log = QTextEdit()
        self.build_log.setReadOnly(True)
        self.build_log.setMaximumHeight(155)
        self.build_log.setPlaceholderText("Native compilation logs appear here. Full log is saved in the launcher data folder.")
        box.addWidget(self.build_log)

    def selected_mod(self):
        i = self.mod_list.currentRow()
        if i < 0:
            raise ValueError("Select a mod first")
        return self.mod_entries[i]

    def mod_details(self, index):
        if not 0 <= index < len(self.mod_entries):
            return
        m = self.mod_entries[index]
        detail = f"{m.name} {m.version} · "
        if m.native:
            detail += f"Native code · {m.metadata['horizon'][:12]} · rebuilt per platform and architecture. Not sandboxed."
        else:
            detail += f"API {m.metadata['api']} · {m.metadata.get('side', 'client')} · capabilities: {', '.join(m.metadata.get('capabilities', [])) or 'none'}. "
            detail += "This upstream manifest format declares no dependency graph; game loading remains the compatibility check."
        self.mod_detail.setText(detail)

    def import_mod(self):
        self.require_idle()
        path, _ = QFileDialog.getOpenFileName(self, "Import Horizon mod", filter="Horizon mods (*.hmod *.hnmod)")
        if path:
            self.launcher.install_mod(Path(path))
            self.refresh()
            self.statusBar().showMessage("Mod imported disabled. Select it and review its capabilities before enabling.")

    def toggle_mod(self):
        self.require_idle()
        mod = self.selected_mod()
        enabled = self.launcher.enabled(mod)
        if not enabled and mod.native and not self.trust_native():
            return
        self.launcher.set_enabled(mod, not enabled)
        self.refresh()

    def remove_mod(self):
        self.require_idle()
        self.launcher.remove_mod(self.selected_mod())
        self.refresh()

    def trust_native(self):
        return QMessageBox.warning(self, "Trust native code?", "Native mods can execute build scripts and game code with your full permissions. Review the source before continuing. Build only mods you trust. A Windows build cannot be reused on macOS.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes

    def rebuild(self):
        self.require_idle()
        source = self.source.text().strip()
        if not source:
            raise ValueError("Set the verified prepared engine source folder in Settings before rebuilding")
        if self.trust_native():
            self.build_log.clear()
            self.start_work(lambda progress: build_native(self.launcher, Path(source), trusted=True, progress=progress),
                            lambda result: self.statusBar().showMessage("Native build completed. PLAY uses this profile's matching binary."))

    def rollback(self):
        self.require_idle()
        for mod in self.launcher.mods():
            if mod.native:
                self.launcher.set_enabled(mod, False)
        self.refresh()

    def shaders_page(self):
        box = self.page("Shaders", "Install a pack, select it, then launch the game. Selection is not proof of rendering compatibility: the game's loader compiles and validates each pack on your GPU.")
        backend = "Metal" if platform.system() == "Darwin" else "Vulkan / DirectX 12 / OpenGL, according to your GPU and settings"
        box.addWidget(QLabel("PLATFORM BACKEND · " + backend))
        self.shader_list = QListWidget()
        box.addWidget(self.shader_list, 1)
        row = QHBoxLayout()
        self.button(row, "Import pack…", self.import_shader)
        self.button(row, "Select pack", self.activate_shader)
        self.button(row, "Restore default shaders", self.disable_shader)
        box.addLayout(row)
        box.addWidget(QLabel("If a pack fails, Horizon falls back to its default renderer.\nUse Restore default shaders to clear the saved selection before relaunching."))
        self.button(box, "Open shader folder", lambda: self.open_path(self.launcher.game / "shaderpacks"))

    def import_shader(self):
        self.require_idle()
        path, _ = QFileDialog.getOpenFileName(self, "Import shader pack", filter="Shader packs (*.zip *.hshader)")
        if path:
            self.launcher.install_shader(Path(path))
            self.refresh()

    def activate_shader(self):
        self.require_idle()
        item = self.shader_list.currentItem()
        if not item:
            raise ValueError("Select a shader pack first")
        self.launcher.select_shader(item.data(Qt.ItemDataRole.UserRole))
        self.refresh()

    def disable_shader(self):
        self.require_idle()
        self.launcher.select_shader("")
        self.refresh()

    def multiplayer_page(self):
        box = self.page("Multiplayer", "Private Tailscale multiplayer uses the existing Herspers joining flow. Both computers must be connected and allowed to reach each other in Tailscale.")
        self.tail_status = QLabel("Tailscale status has not been checked")
        box.addWidget(self.tail_status)
        self.button(box, "Refresh Tailscale status", lambda: self.start_work(lambda progress: tailscale(), self.tail_result))
        form = QFormLayout()
        self.address = QLineEdit()
        self.address.setPlaceholderText("100.80.12.34:25565")
        self.player_name = QLineEdit()
        self.player_name.setText(self.launcher.config.get("player_name", ""))
        form.addRow("Host address", self.address)
        form.addRow("Private player name", self.player_name)
        box.addLayout(form)
        self.server_list = QListWidget()
        self.server_list.currentRowChanged.connect(self.pick_server)
        box.addWidget(self.server_list, 1)
        row = QHBoxLayout()
        self.button(row, "Save favorite", self.save_server)
        self.button(row, "Remove favorite", self.remove_server)
        self.button(row, "JOIN →", self.join)
        box.addLayout(row)
        self.button(box, "Open existing hosting console", self.host)
        box.addWidget(QLabel("Keep the hosting console open; type stop there to save the world.\nThe launcher does not change server authentication or existing server configuration."))

    def tail_result(self, result):
        status = ("CONNECTED · " if result["connected"] else "OFFLINE · ") + result["message"] + " · " + ", ".join(result.get("ips", []))
        self.tail_status.setText(status)
        self.home_tail.setText("Tailscale · " + status)

    def pick_server(self, index):
        if 0 <= index < len(self.launcher.config["servers"]):
            self.address.setText(self.launcher.config["servers"][index])

    def save_server(self):
        self.require_idle()
        address = server_address(self.address.text())
        if address not in self.launcher.config["servers"]:
            self.launcher.config["servers"].append(address)
        self.launcher.save()
        self.refresh()

    def remove_server(self):
        self.require_idle()
        index = self.server_list.currentRow()
        if index >= 0:
            del self.launcher.config["servers"][index]
            self.launcher.save()
            self.refresh()

    def join(self):
        self.launcher.config["player_name"] = self.player_name.text()
        self.launcher.save()
        self.play_game(server=self.address.text(), name=self.player_name.text())

    def host(self):
        self.require_idle()
        installation = self.launcher.installation()
        if platform.system() == "Windows":
            # Launch the existing tested host entrypoint with its interactive EULA prompt.
            subprocess.Popen([str(installation.root / "Herspers-Minecraft.exe"), "--host-tailscale"],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            helper = (Path(sys._MEIPASS) / "herps-host") if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1] / ".cache/herps-host"
            if not helper.is_file():
                raise ValueError("Build the native herps-host helper with tools/package_herps.py before hosting on macOS")
            script = self.launcher.state / "Host-Tailscale.command"
            from .core import atomic
            args = [str(helper), str(installation.binary("horizon-client")), str(self.launcher.support / "resources/26.3"), str(self.launcher.support)]
            atomic(script, ("#!/bin/bash\n" + shlex.join(args) + "\nresult=$?\nread -r -p 'Press Return to close this console. '\nexit \"$result\"\n").encode())
            script.chmod(0o700)
            subprocess.Popen(["/usr/bin/open", "-a", "Terminal", str(script)])

    def settings_page(self):
        box = self.page("Settings", "Keep your game installation and data separate. Default profile reuses existing Herspers saves; new profiles start with their own game folders.")
        form = QFormLayout()
        self.installation_path = QLineEdit(self.launcher.config["installation"])
        self.source = QLineEdit(self.launcher.config.get("native_source", ""))
        self.width, self.height, self.distance = QSpinBox(), QSpinBox(), QSpinBox()
        self.width.setRange(640, 7680)
        self.height.setRange(480, 4320)
        self.distance.setRange(2, 128)
        self.backend = QComboBox()
        self.backend.addItems(["auto"] if platform.system() == "Darwin" else ["auto", "vulkan", "dx12", "opengl"])
        form.addRow("Herspers folder / .app", self.installation_path)
        form.addRow("Prepared native source", self.source)
        form.addRow("Window width", self.width)
        form.addRow("Window height", self.height)
        form.addRow("Render distance", self.distance)
        form.addRow("Renderer (Mac auto = Metal)", self.backend)
        box.addLayout(form)
        row = QHBoxLayout()
        self.button(row, "Find installation…", self.browse_installation)
        self.button(row, "Save settings", self.save_settings)
        box.addLayout(row)
        self.button(box, "Validate installation", self.validate_installation)
        self.button(box, "Open game data and saves", lambda: self.open_path(self.launcher.game))
        self.button(box, "Open mod folder", lambda: self.open_path(self.launcher.game / "horizon-mods"))
        self.button(box, "Restore original graphics settings", self.restore_settings)
        self.button(box, "Switch / update game installation…", self.browse_installation)
        self.button(box, "Roll back to previous installation", self.rollback_installation)
        self.details = QLabel()
        self.details.setWordWrap(True)
        box.addWidget(self.details)
        box.addStretch()

    def browse_installation(self):
        self.require_idle()
        path = QFileDialog.getExistingDirectory(self, "Select Herspers Minecraft folder or .app", options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            from .core import Installation
            installation = Installation.inspect(Path(path))
            self.launcher.config["previous_installation"] = self.launcher.config["installation"]
            self.launcher.config["installation"] = str(installation.root)
            self.launcher.save()
            self.installation_path.setText(str(installation.root))
            self.refresh()

    def save_settings(self):
        self.require_idle()
        from .core import Installation
        installation = Installation.inspect(Path(self.installation_path.text()))
        self.launcher.config.update(installation=str(installation.root), native_source=self.source.text())
        self.launcher.save_graphics(self.width.value(), self.height.value(), self.distance.value(), self.backend.currentText())
        self.launcher.save()
        self.refresh()

    def rollback_installation(self):
        self.require_idle()
        previous = self.launcher.config.get("previous_installation")
        if not previous:
            raise ValueError("No previous installation recorded")
        from .core import Installation
        Installation.inspect(Path(previous))
        self.launcher.config["previous_installation"], self.launcher.config["installation"] = self.launcher.config["installation"], previous
        self.launcher.save()
        self.installation_path.setText(previous)
        self.refresh()

    def validate_installation(self):
        self.require_idle()
        installation = self.launcher.installation()
        self.details.setText(f"Validated Java {GAME} · product {installation.metadata['product_version']} · {installation.metadata['architecture']}\nSource {REVISION}\n{installation.root}")

    def restore_settings(self):
        self.require_idle()
        for name in ("options.txt", "horizon-graphics.txt"):
            path = self.launcher.game / name
            backup = path.with_name(name + ".herps-backup")
            if backup.exists():
                from .core import atomic
                atomic(path, backup.read_bytes())
        self.refresh()

    def open_path(self, path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh(self):
        self.play.setEnabled(not self.busy())
        try:
            self.mod_entries = self.launcher.mods()
            self.mod_list.clear()
            for m in self.mod_entries:
                self.mod_list.addItem(f"{'ON' if self.launcher.enabled(m) else 'OFF'}   {m.name}  {m.version}   ·   {'native build' if m.native else 'runtime / content'}")
            selected = pairs(self.launcher.game / "horizon-graphics.txt").get("pickedShaderPack", "")
            self.summary.setText(f"Java {GAME}  ·  Profile: {self.launcher.config['profile']}\n{sum(self.launcher.enabled(m) for m in self.mod_entries)} active mods  ·  Shader: {selected or 'Default'}")
            self.shader_list.clear()
            for path in sorted((self.launcher.game / "shaderpacks").glob("*")):
                if path.is_file() and path.suffix in (".zip", ".hshader"):
                    self.shader_list.addItem(("SELECTED   " if path.name == selected else "") + path.name + " · rendering unverified")
                    self.shader_list.item(self.shader_list.count() - 1).setData(Qt.ItemDataRole.UserRole, path.name)
            self.server_list.clear()
            self.server_list.addItems(self.launcher.config["servers"])
            self.activity.clear()
            history = self.launcher.state / "activity.json"
            for item in read_json(history) if history.exists() else []:
                self.activity.addItem(f"{item['profile']}   ·   exit {item['exit_code']}   ·   {Path(item['log']).name}")
            options = pairs(self.launcher.game / "options.txt")
            self.width.setValue(int(options.get("overrideWidth", "1280")) or 1280)
            self.height.setValue(int(options.get("overrideHeight", "720")) or 720)
            self.distance.setValue(int(options.get("renderDistance", "12")))
            self.backend.setCurrentText(pairs(self.launcher.game / "horizon-graphics.txt").get("graphicsApi", "auto"))
        except Exception as error:
            self.statusBar().showMessage(str(error))

    def tick(self):
        if self.worker is not None:
            return
        try:
            code = self.launcher.poll()
            if code is not None:
                self.statusBar().showMessage(f"Game exited with code {code}. You can play again. Logs saved in {self.launcher.state}")
                self.refresh()
            elif self.launcher.child:
                self.statusBar().showMessage(f"Herspers is running · PID {self.launcher.child.pid}")
        except Exception as error:
            self.statusBar().showMessage(str(error))

    def closeEvent(self, event):
        if self.busy():
            QMessageBox.information(self, "Operation in progress", "Close the game or wait for the build before closing Herps Launcher. Server consoles must be stopped separately with stop.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Herps Launcher")
    app.setOrganizationName("Herspers")
    app.setStyleSheet(STYLE)
    launcher = Launcher()
    single = QLockFile(str(launcher.state / "window.lock"))
    if not single.tryLock(100):
        QMessageBox.information(None, "Herps Launcher", "Herps Launcher is already open for this game data folder.")
        return 1
    window = Window(launcher)
    window.show()
    return app.exec()
