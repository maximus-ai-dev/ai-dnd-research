"""
git_publish.py — Auto-commit and push after each session.

Called from run.py after site_builder.build_site() completes.
Stages docs/ (built site) and output/ (session reports + wiki source files),
commits with a session message, and pushes to origin.
Errors are raised so run.py can catch and log them.

Requires the project to already be a git repo with a remote named 'origin'.
"""

import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent


def _run(cmd: list[str]) -> str:
    """Run a git command, return stdout. Raises on non-zero exit."""
    result = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(cmd)} failed:\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def publish_site(session_num: int) -> None:
    """Stage docs/, commit, and push to origin/main.

    Args:
        session_num: The session number just completed (used in commit message).
    """
    print(f"[Git] Publishing session {session_num:02d}...")

    # Stage the built site and the source output files (session reports + wiki)
    # Log files are excluded by .gitignore so they won't be staged
    _run(["git", "add", "docs/", "output/"])

    # Check if there's anything to commit
    status = _run(["git", "status", "--porcelain"])
    if not status:
        print("[Git] Nothing to commit — skipping.")
        return

    # Commit with a descriptive message
    message = f"session {session_num:02d}: campaign update"
    _run(["git", "commit", "-m", message])
    print(f"[Git] Committed: {message}")

    # Push — try main first, fall back to master
    try:
        _run(["git", "push", "origin", "main"])
    except RuntimeError:
        _run(["git", "push", "origin", "master"])
    print("[Git] Pushed to origin.")
