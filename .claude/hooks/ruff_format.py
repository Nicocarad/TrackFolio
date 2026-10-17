"""PostToolUse hook: format and lint-fix a Python file right after Claude edits it."""

import json
import os
import subprocess
import sys

path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
if path.endswith(".py"):
    cwd = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        subprocess.run(
            ["uv", "run", "ruff", "format", path], check=False, capture_output=True, cwd=cwd
        )
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "--fix", path],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except OSError as error:
        print(f"ruff hook skipped: {error}", file=sys.stderr)
        sys.exit(0)
    if result.returncode:
        # Exit code 2 feeds stderr back to Claude so it can fix the remaining findings.
        print(result.stdout or result.stderr, file=sys.stderr)
        sys.exit(2)
