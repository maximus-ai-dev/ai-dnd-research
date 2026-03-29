"""
tools.py — Custom tools that agents can use during the session.

CrewAI Concept: Tools
---------------------
Tools are Python functions decorated with @tool that agents can call.
When an agent decides it needs to read a file, roll dice, or update the wiki,
it calls the appropriate tool. CrewAI handles the function-calling protocol
with the LLM automatically.

The @tool decorator takes a name string. The function's docstring becomes the
tool's description that the LLM sees. Parameter type hints tell the LLM what
arguments to provide.

Tools are assigned to agents via the `tools=[...]` parameter.
"""

import json
import random
from pathlib import Path
from crewai.tools import tool

from config import (
    WORLD_DIR, DM_INPUT_FILE, CAMPAIGN_STATE_FILE, WIKI_DIR, SESSIONS_DIR
)


# ===========================================================================
# World & Context Tools — used by the DM to read world files and player input
# ===========================================================================

@tool("Read World Files")
def read_world_files(directory: str = "") -> str:
    """Read all .md and .txt files from the world directory.
    Returns the combined content of all world-building files.
    These files define the campaign setting, lore, and background."""
    world_path = WORLD_DIR
    if not world_path.exists():
        return "No world directory found. The world is a blank canvas."

    content_parts = []
    for ext in ("*.md", "*.txt"):
        for filepath in sorted(world_path.glob(ext)):
            text = filepath.read_text(encoding="utf-8")
            content_parts.append(f"=== {filepath.name} ===\n{text}")

    if not content_parts:
        return "World directory is empty. No lore files found."

    return "\n\n".join(content_parts)


@tool("Read Adventure")
def read_adventure(filepath: str = "") -> str:
    """Read the current adventure file that defines the active quest/scenario.
    Returns the adventure text the DM should follow."""
    from config import CURRENT_ADVENTURE
    if not CURRENT_ADVENTURE.exists():
        return "No adventure file found. Improvise a starting scenario."

    return CURRENT_ADVENTURE.read_text(encoding="utf-8")


@tool("Check DM Input")
def check_dm_input(placeholder: str = "") -> str:
    """Check if the human DM has dropped any ideas or instructions into
    dm_input.txt. If content exists, return it and clear the file.
    The DM agent should weave this into the narrative at the next scene break."""
    if not DM_INPUT_FILE.exists():
        return ""

    content = DM_INPUT_FILE.read_text(encoding="utf-8").strip()
    if content:
        # Clear the file after reading so we don't repeat the input
        DM_INPUT_FILE.write_text("", encoding="utf-8")
        return f"[DM INPUT FROM HUMAN]: {content}"

    return ""


# ===========================================================================
# Campaign State Tools — save/load persistent state between sessions
# ===========================================================================

@tool("Load Campaign State")
def load_campaign_state(placeholder: str = "") -> str:
    """Load the current campaign state (session number, party HP, inventory,
    location, quest progress). Returns the state as a JSON string."""
    if not CAMPAIGN_STATE_FILE.exists():
        return "{}"

    return CAMPAIGN_STATE_FILE.read_text(encoding="utf-8")


@tool("Save Campaign State")
def save_campaign_state(state_json: str) -> str:
    """Save the updated campaign state to campaign_state.json.
    Accepts a JSON string with session_number, current_location, party info,
    story_summary, active_quests, etc."""
    try:
        # First try: parse as-is
        state = json.loads(state_json)
    except json.JSONDecodeError:
        # DeepSeek sometimes wraps JSON in markdown fences or adds trailing text.
        # Try to extract the JSON object from whatever mess we got.
        import re
        match = re.search(r'\{[\s\S]*\}', state_json)
        if match:
            try:
                state = json.loads(match.group())
            except json.JSONDecodeError as e:
                return (
                    f"Error saving state — could not parse JSON: {e}\n"
                    "Tip: send a plain JSON object, no markdown fences or extra text."
                )
        else:
            return (
                "Error saving state — no JSON object found in input.\n"
                "Tip: send a plain JSON object like {\"session_number\": 1, ...}"
            )

    CAMPAIGN_STATE_FILE.write_text(
        json.dumps(state, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )
    return "Campaign state saved successfully."


# ===========================================================================
# Dice Rolling Tool — used by PCs and the Rules Adjudicator
# ===========================================================================

@tool("Roll Dice")
def roll_dice(notation: str) -> str:
    """Roll dice using standard D&D notation like '1d20', '2d6+3', '1d20+5'.
    Supports: XdY, XdY+Z, XdY-Z, advantage (2d20kh1), disadvantage (2d20kl1).
    Returns the individual rolls and the total."""
    notation = notation.strip().lower()

    # Handle advantage/disadvantage shorthand
    if notation in ("advantage", "adv"):
        notation = "2d20kh1"
    elif notation in ("disadvantage", "dis", "disadv"):
        notation = "2d20kl1"

    # Parse modifier (+/- at the end)
    modifier = 0
    base = notation
    if "+" in notation and "kh" not in notation and "kl" not in notation:
        parts = notation.split("+")
        base = parts[0]
        modifier = int(parts[1])
    elif "-" in notation and "kh" not in notation and "kl" not in notation:
        parts = notation.split("-")
        base = parts[0]
        modifier = -int(parts[1])

    # Parse keep-highest / keep-lowest
    keep_high = None
    keep_low = None
    if "kh" in base:
        parts = base.split("kh")
        base = parts[0]
        keep_high = int(parts[1]) if parts[1] else 1
    elif "kl" in base:
        parts = base.split("kl")
        base = parts[0]
        keep_low = int(parts[1]) if parts[1] else 1

    # Parse XdY
    if "d" not in base:
        return f"Invalid notation: {notation}. Use format like '1d20' or '2d6+3'."

    try:
        num_dice, die_size = base.split("d")
        num_dice = int(num_dice) if num_dice else 1
        die_size = int(die_size)
    except ValueError:
        return f"Invalid notation: {notation}. Use format like '1d20' or '2d6+3'."

    # Roll the dice
    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    kept = rolls[:]

    if keep_high is not None:
        kept = sorted(rolls, reverse=True)[:keep_high]
    elif keep_low is not None:
        kept = sorted(rolls)[:keep_low]

    total = sum(kept) + modifier

    # Format result
    result = f"Rolled {notation}: {rolls}"
    if keep_high or keep_low:
        result += f" -> kept {kept}"
    if modifier > 0:
        result += f" + {modifier}"
    elif modifier < 0:
        result += f" - {abs(modifier)}"
    result += f" = **{total}**"

    return result


# ===========================================================================
# Wiki Tools — used by the Wiki Keeper to maintain the Obsidian knowledge base
#
# One file per entity (NPC, location, item, faction, event, etc.)
# Files are named after the entity: "Reyna Steelforge.md", "The Second Wind Inn.md"
# Each file has YAML frontmatter + structured markdown body.
# Proper nouns in file bodies use Obsidian [[wiki links]].
# ===========================================================================

def _wiki_filename(entity_name: str) -> str:
    """Normalize an entity name to a .md filename."""
    name = entity_name.strip()
    if not name.endswith(".md"):
        name += ".md"
    return name


@tool("Read Wiki File")
def read_wiki_file(entity_name: str) -> str:
    """Read the wiki file for a specific entity.

    entity_name: the exact name of the entity (e.g. 'Reyna Steelforge',
                 'The Second Wind Inn', 'Dreamstone').
    Returns the file content, or 'File does not exist.' if not yet created."""
    wiki_file = WIKI_DIR / _wiki_filename(entity_name)
    if not wiki_file.exists():
        return "File does not exist."
    return wiki_file.read_text(encoding="utf-8")


@tool("Write Wiki File")
def write_wiki_file(entity_name: str, content: str) -> str:
    """Create a brand-new wiki file for an entity.
    Only call this after Read Wiki File returned 'File does not exist.'

    entity_name: the exact name of the entity (e.g. 'Reyna Steelforge').
    content: the COMPLETE file content — YAML frontmatter + markdown body.

    Content must follow this template:
    ---
    type: npc | location | item | faction | event | lore
    location: [[Place Name]]   (omit if not applicable)
    status: alive | dead | unknown | exists | destroyed  (omit if not applicable)
    ---
    # Entity Name
    **Description:** One-sentence summary.
    **History:** What happened involving this entity."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    filename = _wiki_filename(entity_name)
    wiki_file = WIKI_DIR / filename
    if wiki_file.exists():
        return (
            f"'{filename}' already exists. "
            "Use Append Wiki File to add new session information instead."
        )
    wiki_file.write_text(content, encoding="utf-8")
    return f"Wiki file '{filename}' created successfully."


@tool("Append Wiki File")
def append_wiki_file(entity_name: str, content: str) -> str:
    """Append new session information to an existing wiki file.
    Only call this after Read Wiki File returned existing content.

    entity_name: the exact name of the entity (e.g. 'Reyna Steelforge').
    content: the new information to add (markdown, will be appended after a
             separator — do NOT repeat the YAML frontmatter or existing text)."""
    filename = _wiki_filename(entity_name)
    wiki_file = WIKI_DIR / filename
    if not wiki_file.exists():
        return (
            f"'{filename}' does not exist. "
            "Use Write Wiki File to create it first."
        )
    existing = wiki_file.read_text(encoding="utf-8")
    updated = existing.rstrip() + "\n\n---\n\n" + content
    wiki_file.write_text(updated, encoding="utf-8")
    return f"Wiki file '{filename}' updated successfully."


# ===========================================================================
# Session Blog Tool — used by the Scribe to write narrative session logs
# ===========================================================================

@tool("Write Session Blog")
def write_session_blog(session_number: int, content: str) -> str:
    """Write a session blog post as a markdown file.

    session_number: the session number (used in filename, e.g. 1 → session_01.md)
    content: the full markdown content of the session narrative"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"session_{session_number:02d}.md"
    filepath = SESSIONS_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    return f"Session blog saved to {filepath}"


@tool("Read Previous Session")
def read_previous_session(session_number: int) -> str:
    """Read a previous session blog for continuity reference.
    Returns the content of the specified session file."""
    filepath = SESSIONS_DIR / f"session_{session_number:02d}.md"
    if not filepath.exists():
        return f"No session {session_number} found."
    return filepath.read_text(encoding="utf-8")
