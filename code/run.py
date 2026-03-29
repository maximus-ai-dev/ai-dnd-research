"""
run.py — Entry point for the AI D&D Campaign System.

Usage:
    python run.py                    # Full session with Claude as DM
    python run.py --dry-run          # Quick 3-exchange test session
    python run.py --dm-model deepseek  # Use DeepSeek for the DM
    python run.py --dry-run --dm-model deepseek  # Test with DeepSeek DM

CrewAI Concept: Putting It All Together
---------------------------------------
This file doesn't use any CrewAI-specific code — it just parses CLI args
and calls session.run_session(). The CrewAI magic happens inside session.py,
agents.py, and tools.py:

  run.py (CLI args)
    → session.py (orchestration loop)
      → agents.py (Agent definitions with LLM configs)
      → tools.py (@tool decorated functions)
      → CrewAI Crew/Task (mini-crews for each game turn)
"""

import argparse
import json
import sys
from datetime import datetime

from config import ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, CAMPAIGN_STATE_FILE, SESSIONS_DIR, LOGS_DIR


class TeeWriter:
    """Duplicates all writes to both the terminal and a log file.

    This captures everything printed during the session — DM narration,
    player responses, errors, CrewAI internal messages — so you have a
    complete raw record for debugging and reference.
    """

    def __init__(self, log_path, original_stream):
        self.log_file = open(log_path, "w", encoding="utf-8")
        self.original = original_stream
        # Write a header with timestamp
        self.log_file.write(f"=== Session Log — {datetime.now().isoformat()} ===\n\n")

    def write(self, text):
        # Write to terminal (handle encoding errors gracefully on Windows)
        try:
            self.original.write(text)
        except UnicodeEncodeError:
            self.original.write(text.encode("ascii", errors="replace").decode())
        # Always write full unicode to the log file
        self.log_file.write(text)
        self.log_file.flush()

    def flush(self):
        self.original.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()

    # Pass through any other attribute access to the original stream
    # (some libraries check for .encoding, .isatty(), etc.)
    def __getattr__(self, name):
        return getattr(self.original, name)


def main():
    parser = argparse.ArgumentParser(
        description="AI D&D Campaign System — autonomous AI-run D&D 5e sessions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a short test session (3 exchanges instead of 10)",
    )
    parser.add_argument(
        "--dm-model",
        choices=["claude", "deepseek"],
        default="claude",
        help="Which LLM to use for the Dungeon Master (default: claude)",
    )
    parser.add_argument(
        "--all-deepseek",
        action="store_true",
        help="Use DeepSeek for ALL agents (cheapest option, ~$0.05/session)",
    )

    args = parser.parse_args()

    # --- Validate API keys ---
    dm_use_claude = (args.dm_model == "claude")

    # --all-deepseek only needs DeepSeek key
    if args.all_deepseek:
        if not DEEPSEEK_API_KEY:
            print("ERROR: DEEPSEEK_API_KEY not set in .env file.")
            print("Copy .env.example to .env and add your key.")
            sys.exit(1)
    else:
        if dm_use_claude and not ANTHROPIC_API_KEY:
            print("ERROR: ANTHROPIC_API_KEY not set in .env file.")
            print("The DM and creative agents (Scribe, Wiki Keeper) need this key.")
            print("Copy .env.example to .env and add your key.")
            sys.exit(1)

        if not DEEPSEEK_API_KEY:
            print("ERROR: DEEPSEEK_API_KEY not set in .env file.")
            print("Player characters and rules agents need this key.")
            print("Copy .env.example to .env and add your key.")
            sys.exit(1)

    # --- Set up raw terminal logging ---
    # Figure out the next session number so the log file matches
    try:
        state = json.loads(CAMPAIGN_STATE_FILE.read_text(encoding="utf-8"))
        next_session = state.get("session_number", 0) + 1
    except (FileNotFoundError, json.JSONDecodeError):
        next_session = 1

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"session_{next_session:02d}_log.txt"

    # Tee both stdout and stderr to the log file
    stdout_tee = TeeWriter(log_path, sys.stdout)
    stderr_tee = TeeWriter(log_path, sys.stderr)
    sys.stdout = stdout_tee
    sys.stderr = stderr_tee

    print(f"[Log] Raw terminal output being saved to: {log_path}\n")

    # --- Silence CrewAI internal event pairing warnings ---
    try:
        from crewai.events.event_context import (
            _event_context_config, EventContextConfig, MismatchBehavior,
        )
        _event_context_config.set(EventContextConfig(
            mismatch_behavior=MismatchBehavior.SILENT,
            empty_pop_behavior=MismatchBehavior.SILENT,
        ))
    except ImportError:
        pass  # Older CrewAI version without this module

    try:
        # --- Run the session ---
        from session import run_session
        run_session(dm_use_claude=dm_use_claude, dry_run=args.dry_run,
                    all_deepseek=args.all_deepseek)

        # --- Rebuild the static site ---
        # Runs after every session. Errors here never block the next session.
        try:
            from site_builder import build_site
            build_site()
        except Exception as site_err:
            print(f"[Site] Warning: site build failed ({site_err}). Skipping.")

        # --- Auto commit + push to GitHub ---
        try:
            from git_publish import publish_site
            publish_site(session_num=next_session)
        except Exception as git_err:
            print(f"[Git] Warning: publish failed ({git_err}). Skipping.")

    finally:
        # Restore original streams and close log files
        sys.stdout = stdout_tee.original
        sys.stderr = stderr_tee.original
        stdout_tee.close()
        stderr_tee.close()
        print(f"\n[Log] Full terminal log saved to: {log_path}")


if __name__ == "__main__":
    main()
