"""
config.py — Central configuration for the AI D&D Campaign System.

This module handles:
- Loading API keys from .env
- Defining which LLM each agent uses
- Project-wide paths and constants

CrewAI Concept: LLM Configuration
----------------------------------
CrewAI uses the LLM() class to configure language models per agent.
The model string format is "provider/model-name":
  - "anthropic/claude-sonnet-4-20250514" → Anthropic's Claude
  - "deepseek/deepseek-chat" → DeepSeek's chat model

Each agent can use a different LLM, letting you balance cost vs quality.
Creative agents (Scribe, Wiki Keeper) get Claude for better writing.
Mechanical agents (dice rolling, rules) get DeepSeek for cost savings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------
# CrewAI routes through litellm, so model strings follow litellm's format:
#   "anthropic/<model>" for Anthropic
#   "deepseek/<model>" for DeepSeek (uses OpenAI-compatible API)
CLAUDE_MODEL = "anthropic/claude-sonnet-4-20250514"
DEEPSEEK_MODEL = "deepseek/deepseek-chat"

# ---------------------------------------------------------------------------
# Project paths — all relative to this file's directory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent

WORLD_DIR = BASE_DIR / "world"
ADVENTURES_DIR = BASE_DIR / "adventures"
CURRENT_ADVENTURE = ADVENTURES_DIR / "current_adventure.md"
CAMPAIGN_ARC_FILE = BASE_DIR / "campaign_arc.md"
DM_INPUT_FILE = BASE_DIR / "dm_input.txt"
CAMPAIGN_STATE_FILE = BASE_DIR / "campaign_state.json"

OUTPUT_DIR = BASE_DIR / "output"
SESSIONS_DIR = OUTPUT_DIR / "sessions"
WIKI_DIR = OUTPUT_DIR / "wiki"
REVIEWS_DIR = OUTPUT_DIR / "reviews"
LOGS_DIR = OUTPUT_DIR / "logs"

# ---------------------------------------------------------------------------
# Session settings
# ---------------------------------------------------------------------------
# How many DM↔Player exchanges per session (each exchange = DM narrates,
# all 3 PCs respond). --dry-run overrides this to 3.
# 20-session format: one adventure per session. 20 exchanges gives the DM
# enough room to tell a complete adventure story without padding or rushing.
# The DM's session-end detection can stop early if the adventure resolves
# before exchange 20.
DEFAULT_EXCHANGES = 20
DRY_RUN_EXCHANGES = 3
