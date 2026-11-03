"""Exercise real Qt widgets offscreen when the optional UI dependencies exist."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from herps_launcher.app import Window, STYLE
except ImportError:
    QApplication = None

from herps_launcher.core import Launcher


@unittest.skipIf(QApplication is None, "Install herps_launcher/requirements.txt for desktop integration tests")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.launcher = Launcher(Path(self.temporary.name))
        self.window = Window(self.launcher)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window.worker:
            self.window.worker.wait(10000)
            self.app.processEvents()
        if self.launcher.child:
            self.launcher.child.wait(timeout=10)
            self.launcher.poll()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def test_all_five_sidebar_buttons_navigate_actual_pages(self):
        for i, button in enumerate(self.window.nav):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(self.window.pages.currentIndex(), i)
            self.assertTrue(button.isChecked())

    def test_profile_selection_changes_game_directory_and_persists(self):
        original = self.launcher.game
        self.launcher.add_profile("creative")
        self.window.profile.addItem("creative")
        self.window.profile.setCurrentText("creative")
        self.app.processEvents()
        self.assertNotEqual(self.launcher.game, original)
        self.assertEqual(Launcher(self.launcher.support).config["profile"], "creative")
        self.assertIn("creative", self.window.summary.text())

    def test_tailscale_result_is_visible_on_home_and_multiplayer(self):
        self.window.tail_result({"connected": True, "message": "Running", "ips": ["100.80.12.34"]})
        self.assertIn("100.80.12.34", self.window.home_tail.text())
        self.assertIn("CONNECTED", self.window.tail_status.text())

    def test_favorite_server_is_saved_and_selected_through_widgets(self):
        self.window.address.setText("100.80.12.34:25565")
        self.window.save_server()
        self.window.address.clear()
        self.window.server_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(self.window.address.text(), "100.80.12.34:25565")
        self.assertEqual(Launcher(self.launcher.support).config["servers"], ["100.80.12.34:25565"])

    def test_play_button_runs_worker_and_reenables_after_exit(self):
        # The owned process fixture is exercised in the core suite on POSIX.
        # Here the actual button/worker/timer lifecycle is the integration under test.
        completed = []
        def launched(server, name, clean):
            completed.append((server, name, clean))
        with patch.object(self.launcher, "launch", side_effect=launched):
            QTest.mouseClick(self.window.play, Qt.MouseButton.LeftButton)
            self.assertFalse(self.window.play.isEnabled())
            deadline = time.monotonic() + 5
            while self.window.worker and time.monotonic() < deadline:
                QTest.qWait(10)
                self.app.processEvents()
            self.assertIsNone(self.window.worker)
            self.assertEqual(completed, [("", "", False)])
            self.assertTrue(self.window.play.isEnabled())


if __name__ == "__main__":
    unittest.main()
