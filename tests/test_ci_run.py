"""CI diagnostics must preserve command behavior and surface useful failures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WRAPPER = Path(__file__).resolve().parents[1] / "tools/ci_run.py"


class CiRunTests(unittest.TestCase):
    def test_literal_arguments_and_both_output_streams_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "test.log"
            arguments = ["a path with spaces", "$(literal)", "`literal`", "--option"]
            result = subprocess.run([sys.executable, str(WRAPPER), str(log), sys.executable,
                "-c", "import json,sys; print(json.dumps(sys.argv[1:])); print('stderr-marker',file=sys.stderr)",
                *arguments], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(json.dumps(arguments), log.read_text())
            self.assertIn("stderr-marker", log.read_text())
            self.assertIn("stderr-marker", result.stdout)
            self.assertNotIn("::error", result.stdout)

    def test_failure_exit_and_full_log_survive_bounded_escaped_annotation(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "test.log"
            result = subprocess.run([sys.executable, str(WRAPPER), str(log), sys.executable,
                "-c", "import sys; print('start-marker'); print('x'*4000); print('failure 100%\\ntraceback-marker'); sys.exit(7)"],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 7)
            self.assertIn("start-marker", log.read_text())
            self.assertGreater(len(log.read_text()), 4000)
            annotation = [line for line in result.stdout.splitlines() if line.startswith("::error")][0]
            self.assertIn("100%25%0Atraceback-marker", annotation)
            self.assertNotIn("start-marker", annotation)
            self.assertLess(len(annotation), 2700)

    def test_unavailable_command_reports_start_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "test.log"
            missing = str(Path(directory) / "command-that-does-not-exist")
            result = subprocess.run([sys.executable, str(WRAPPER), str(log), missing],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 127)
            self.assertIn("Could not start command", log.read_text())
            self.assertIn("::error", result.stdout)


if __name__ == "__main__":
    unittest.main()
