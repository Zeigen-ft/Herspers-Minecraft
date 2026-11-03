#!/usr/bin/env python3
"""Run literal command arguments, tee its output, and annotate the failure tail."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def annotate(text: str) -> None:
    message = text[-2500:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Command failed::" + message, flush=True)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("Usage: ci_run.py LOG-PATH COMMAND [ARG ...]", file=sys.stderr)
        return 2
    log_path, command = Path(args[0]), args[1:]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tail = ""
    with log_path.open("w", encoding="utf-8", newline="") as log:
        try:
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace") as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    tail = (tail + line)[-2500:]
                result = process.wait()
        except OSError as error:
            tail = f"Could not start command: {error}\n"
            log.write(tail)
            result = 127
    if result:
        annotate(tail or f"Command exited with status {result}; see {log_path}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
