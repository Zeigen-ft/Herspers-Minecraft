"""PyInstaller entrypoint; imports shared code without relative entrypoint imports."""
import sys
import json
from herps_launcher.app import main

if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        import tempfile
        from pathlib import Path
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from herps_launcher.app import Window, STYLE
        from herps_launcher.core import Launcher
        report = {"status": "failed", "pages_opened": 0}
        result = 1
        try:
            app = QApplication([])
            app.setStyleSheet(STYLE)
            with tempfile.TemporaryDirectory() as temporary:
                launcher = Launcher(Path(temporary))
                if "--require-installation" in sys.argv:
                    installation = launcher.installation()
                    report["installation"] = str(installation.root)
                    report["architecture"] = installation.metadata["architecture"]
                window = Window(launcher)
                window.show()
                for i, button in enumerate(window.nav):
                    QTest.mouseClick(button, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
                    app.processEvents()
                    assert window.pages.currentIndex() == i, f"Page {i} did not open"
                    report["pages_opened"] += 1
                window.close()
            report["status"] = "passed"
            result = 0
        except Exception as error:
            report["error"] = str(error)
        if "--smoke-report" in sys.argv:
            report_path = Path(sys.argv[sys.argv.index("--smoke-report") + 1])
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        raise SystemExit(result)
    raise SystemExit(main())
