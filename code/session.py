"""
session.py — The session orchestrator that runs a full D&D session.

CrewAI Concept: Crew & Process
-------------------------------
A Crew groups agents + tasks and defines how they collaborate.
Process types:
  - Process.sequential: tasks run in order, output chains to the next
  - Process.hierarchical: a manager agent delegates (buggy in practice)

OUR APPROACH: Instead of one big Crew, we create small Crews for each
"turn" of the game. This gives us full control over the conversation loop:

  1. DM Crew: DM agent narrates a scene (reads world, adventure, DM input)
  2. PC Crew: All 3 PCs respond to the DM's narration (sequential)
  3. Rules Crew: If a contested action or check is needed, adjudicate it
  4. Combat Crew: If combat triggers, run a combat encounter
  5. Scribe Crew: At session end, write the narrative blog
  6. Wiki Crew: At session end, update the wiki

Each "crew" is really just us calling agent.execute_task() or creating
a mini Crew with a single task. The session loop in Python ties it together.

CrewAI Concept: Tasks
---------------------
A Task tells an agent WHAT to do:
  - description: the detailed instructions for this specific job
  - expected_output: what the result should look like
  - agent: which agent handles it
  - context: list of prior tasks whose output feeds into this one
"""

import json
from crewai import Agent, Task, Crew, Process
import shutil
from config import (
    CAMPAIGN_STATE_FILE, DEFAULT_EXCHANGES, DRY_RUN_EXCHANGES,
    WORLD_DIR, DM_INPUT_FILE, CURRENT_ADVENTURE, CAMPAIGN_ARC_FILE,
    WIKI_DIR, ADVENTURES_DIR, SESSIONS_DIR, REVIEWS_DIR, LOGS_DIR,
)
from leveling import level_up_party
from agents import (
    create_dm_agent, create_pc_agents, create_rules_keeper,
    create_scribe, create_wiki_keeper, create_lorekeeper, create_editor,
    create_enemy_agent,
)
from enemy_encounters import get_encounter, has_encounter


# API call counter — tracks total calls per session for cost analysis
_api_call_count = 0

def run_single_agent_task(agent: Agent, description: str,
                          expected_output: str,
                          min_words: int = 15, max_retries: int = 2) -> str:
    """Run a single task with a single agent and return the output.

    CrewAI Concept: This creates a mini Crew with one agent and one task.
    We use Process.sequential since there's only one task. The crew.kickoff()
    method runs the task and returns the result.

    Includes automatic retry logic for garbage responses (DeepSeek sometimes
    returns empty strings, '**', or other sub-15-word garbage). Retries up to
    max_retries times before returning whatever it got.

    This is the building block we use to orchestrate the session loop.
    """
    for attempt in range(1, max_retries + 2):  # +2 because range is exclusive & attempt 1 is the first try
        task = Task(
            description=description,
            expected_output=expected_output,
            agent=agent,
        )

        # A Crew needs at least one agent and one task.
        # Even for a single agent, we wrap it in a Crew so CrewAI handles
        # the LLM calling, tool usage, and output formatting.
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,  # reduce noise in the main loop
        )

        try:
            result = crew.kickoff()
        except Exception as e:
            error_msg = str(e).lower()
            is_connection_error = any(term in error_msg for term in [
                "winerror 10054", "connection was forcibly closed",
                "readtimeout", "read timed out", "connecttimeout",
                "internal server error", "internalservererror",
                "502", "503", "429",
            ])
            if is_connection_error and attempt <= max_retries:
                import time
                wait_secs = 10 * attempt  # 10s, 20s on second retry
                print(f"  [Retry] API connection error: {str(e)[:100]}...")
                print(f"  [Retry] Waiting {wait_secs}s then retrying ({attempt}/{max_retries})...")
                time.sleep(wait_secs)
                continue
            else:
                raise  # Re-raise if not a connection error or out of retries

        global _api_call_count
        _api_call_count += 1

        output = result.raw.strip() if result.raw else ""

        # Accept valid short responses (e.g., dead characters)
        VALID_SHORT_RESPONSES = [
            "dead", "no response possible", "unconscious",
            "no actions", "cannot act", "incapacitated",
        ]
        output_lower = output.lower()
        if any(signal in output_lower for signal in VALID_SHORT_RESPONSES):
            return output  # Valid short response, not garbage

        # Check for garbage output
        word_count = len(output.split())

        # Detect hallucination loops: if any single line repeats 5+ times,
        # the model is stuck in a degenerate repetition state. Treat as
        # garbage regardless of word count. This prevents burning API credits
        # on infinite loops (observed in Run 4 S9 Editor review).
        is_loop = False
        if word_count >= min_words:
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            if lines:
                from collections import Counter
                line_counts = Counter(lines)
                most_common_count = line_counts.most_common(1)[0][1]
                if most_common_count >= 5 and most_common_count > len(lines) * 0.5:
                    is_loop = True
                    print(f"  [Warning] Hallucination loop detected: one line repeated "
                          f"{most_common_count}/{len(lines)} times. Treating as garbage.")

        if word_count >= min_words and not is_loop:
            return output  # Good response

        if attempt <= max_retries:
            print(f"  [Retry] Agent returned garbage ({word_count} words: "
                  f"'{output[:50]}...'). Retrying ({attempt}/{max_retries})...")
        else:
            print(f"  [Warning] Agent returned garbage after {max_retries} retries. "
                  f"Using last response.")
            return output


def load_state() -> dict:
    """Load campaign state from JSON file."""
    try:
        return json.loads(CAMPAIGN_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"session_number": 0, "party": {}, "current_location": "Unknown"}


def save_state(state: dict):
    """Save campaign state to JSON file."""
    CAMPAIGN_STATE_FILE.write_text(
        json.dumps(state, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )


def advance_adventure(state: dict, party_levels: dict = None) -> bool:
    """Check if the current adventure is complete and swap to the next one.

    Called at the end of each session after state is saved. If the party has
    played through all sessions for the current adventure, this function:
      1. Increments current_adventure
      2. Resets sessions_in_adventure to 0
      3. Copies the next adventure file to current_adventure.md
      4. Saves the updated state

    Adventure files follow the naming convention:
        adventures/adventure_XX_<name>.md
    where XX is the zero-padded adventure number (01, 02, etc.)

    Returns True if an adventure swap occurred, False otherwise.
    """
    sessions_done = state.get("sessions_in_adventure", 0)
    max_sessions = state.get("max_sessions_per_adventure", 3)

    if sessions_done < max_sessions:
        return False

    # Adventure complete!
    current_num = state.get("current_adventure", 1)
    next_num = current_num + 1

    # Find the next adventure file by glob pattern
    pattern = f"adventure_{next_num:02d}_*.md"
    matches = sorted(ADVENTURES_DIR.glob(pattern))

    if not matches:
        print(f"\n[Adventure] Adventure {current_num} complete! Campaign finished!")
        print(f"[Adventure] No adventure file found matching '{pattern}'.")
        # Mark adventure as complete by advancing current_adventure past it
        state["current_adventure"] = next_num
        state["sessions_in_adventure"] = 0
        save_state(state)
        return True

    next_adventure_file = matches[0]
    next_name = next_adventure_file.stem.replace(f"adventure_{next_num:02d}_", "").replace("_", " ").title()

    # Copy the new adventure to current_adventure.md
    shutil.copy2(next_adventure_file, CURRENT_ADVENTURE)

    # Reassert Python-authoritative party levels before leveling
    # (DM may have changed them during its state save)
    if party_levels:
        for pc_name, pc_data in state.get("party", {}).items():
            pc_data["level"] = party_levels.get(pc_name, pc_data.get("level", 1))

    # Level up the party (milestone leveling — also resets HP to new max)
    level_summary = level_up_party(state)

    # Reset conditions for all PCs (long rest between adventures)
    for pc_name, pc_data in state.get("party", {}).items():
        pc_data["conditions"] = "Fully rested, long rest completed between adventures"

    # Update state
    state["current_adventure"] = next_num
    state["current_adventure_name"] = next_name
    state["sessions_in_adventure"] = 0
    save_state(state)

    print(f"\n{'='*60}")
    print(f"  ADVENTURE COMPLETE!")
    print(f"  Adventure {current_num} finished.")
    print(f"  Swapping to Adventure {next_num}: {next_name}")
    print(f"  File: {next_adventure_file.name}")
    print(f"  --- LEVEL UP ---")
    for pc_name, info in level_summary.items():
        print(f"  {pc_name}: {info}")
    print(f"{'='*60}\n")

    return True


def condense_story_summary(state: dict, dm_agent: Agent = None) -> str:
    """Condense the story_summary field to key plot points only.

    Called when an adventure completes. Uses an LLM agent to intelligently
    distill the summary down to ~150 words of essential plot points.
    Falls back to Python-side truncation if no agent is available.

    Returns the condensed summary string.
    """
    current_summary = state.get("story_summary", "")
    if not current_summary:
        return current_summary

    # Build a comprehensive source from adventure summaries + current summary
    # so the condenser never loses track of completed adventures.
    adventure_summaries = state.get("adventure_summaries", {})
    if adventure_summaries:
        adv_lines = "\n".join(
            f"- Adventure {k}: {v}" for k, v in sorted(adventure_summaries.items(), key=lambda x: int(x[0]))
        )
        source_material = (
            f"ADVENTURE SUMMARIES (authoritative):\n{adv_lines}\n\n"
            f"CURRENT RUNNING SUMMARY:\n{current_summary}"
        )
    else:
        source_material = current_summary

    # If the summary is already short and covers all adventures, skip
    word_count = len(current_summary.split())
    adventures_covered = len(adventure_summaries)
    if word_count <= 200 and adventures_covered <= 5:
        print(f"[Summary] Already concise ({word_count} words). Skipping condensing.")
        return current_summary

    if dm_agent is not None:
        print(f"[Summary] Condensing story summary ({word_count} words, {adventures_covered} adventures → ~200 words)...")
        condensed = run_single_agent_task(
            agent=dm_agent,
            description=(
                "You are condensing a campaign story summary. Using ALL the source "
                "material below, write a single flowing paragraph of ~200 words that "
                "covers the ENTIRE campaign from Adventure 1 through the most recent. "
                "Every adventure must be represented. Keep ONLY:\n"
                "- Key plot points and major events from each adventure\n"
                "- Important decisions the party made\n"
                "- Current objectives and unresolved threats\n"
                "- Names of important NPCs, locations, and factions\n\n"
                "Drop ALL:\n"
                "- Combat play-by-play and tactical details\n"
                "- Minor NPC interactions and dialogue\n"
                "- Travel descriptions and atmospheric details\n"
                "- Session-by-session structure (merge into one flowing paragraph)\n\n"
                f"{source_material}\n\n"
                "Output ONLY the condensed summary paragraph. No preamble, no explanation."
            ),
            expected_output=(
                "A single concise paragraph (~200 words) capturing the essential "
                "plot points of the entire campaign so far."
            ),
        )
        condensed = condensed.strip()
        new_word_count = len(condensed.split())
        print(f"[Summary] Condensed: {word_count} → {new_word_count} words.")
        return condensed
    else:
        # Fallback: hard truncate to last ~200 words with a note
        print(f"[Summary] No agent available. Hard-truncating to ~200 words.")
        words = current_summary.split()
        truncated = " ".join(words[-200:])
        return f"[Earlier events condensed] ...{truncated}"


def extract_session_section(adventure_text: str, session_num: int) -> str:
    """Extract only the relevant session section from the adventure file.

    Adventure files contain all sessions (e.g. ## Session 1: ..., ## Session 2: ...).
    Giving DeepSeek the full file causes it to read future session content and skip ahead.
    This function extracts ONLY the preamble (overview, pacing rules) plus the current
    session's section, preventing content bleed from future sessions.

    Returns the filtered adventure text.
    """
    lines = adventure_text.splitlines()
    result = []
    in_target_session = False
    in_future_session = False
    target_header = f"## Session {session_num}:"

    for line in lines:
        stripped = line.strip()

        # Detect session headers (## Session N: ...)
        if stripped.startswith("## Session "):
            # Extract session number from header
            try:
                header_num = int(stripped.split("## Session ")[1].split(":")[0].strip())
            except (IndexError, ValueError):
                header_num = None

            if header_num is not None:
                if header_num == session_num:
                    in_target_session = True
                    in_future_session = False
                elif header_num > session_num:
                    in_target_session = False
                    in_future_session = True
                else:
                    # Past sessions — include (they've already happened)
                    in_target_session = False
                    in_future_session = False

        if not in_future_session:
            result.append(line)

    return "\n".join(result)


def preload_dm_context() -> dict:
    """Read world files, adventure, campaign arc, and DM input directly in Python.

    Why: DeepSeek sometimes outputs "I'll gather context now..." as its final
    answer instead of actually calling tools. Pre-loading the context here and
    injecting it straight into the task description sidesteps that problem —
    the DM just receives the full context and only needs to write narration.

    Returns a dict with keys: world, adventure, arc, dm_input, state,
                               arc_beat, sessions_in_beat
    """
    # World files
    if WORLD_DIR.exists():
        parts = []
        for ext in ("*.md", "*.txt"):
            for filepath in sorted(WORLD_DIR.glob(ext)):
                text = filepath.read_text(encoding="utf-8")
                parts.append(f"=== {filepath.name} ===\n{text}")
        world_text = "\n\n".join(parts) if parts else "No world files found."
    else:
        world_text = "No world directory found. The world is a blank canvas."

    # Current adventure (full text — caller will extract the relevant session section)
    if CURRENT_ADVENTURE.exists():
        adventure_text = CURRENT_ADVENTURE.read_text(encoding="utf-8")
    else:
        adventure_text = "No adventure file found. Improvise a starting scenario."

    # Campaign arc (the long-form act/beat structure the DM always references)
    if CAMPAIGN_ARC_FILE.exists():
        arc_text = CAMPAIGN_ARC_FILE.read_text(encoding="utf-8")
    else:
        arc_text = ""

    # Human DM input (consume it so it isn't re-read)
    dm_input_text = ""
    if DM_INPUT_FILE.exists():
        raw = DM_INPUT_FILE.read_text(encoding="utf-8").strip()
        if raw:
            DM_INPUT_FILE.write_text("", encoding="utf-8")
            dm_input_text = raw

    # Campaign state — also extract beat-tracking fields for Python-side logic
    state_text = CAMPAIGN_STATE_FILE.read_text(encoding="utf-8") if CAMPAIGN_STATE_FILE.exists() else "{}"
    try:
        state_data = json.loads(state_text)
    except json.JSONDecodeError:
        state_data = {}
    arc_beat = state_data.get("next_beat", "")
    sessions_in_beat = state_data.get("sessions_in_current_beat", 0)

    return {
        "world": world_text,
        "adventure": adventure_text,
        "arc": arc_text,
        "dm_input": dm_input_text,
        "state": state_text,
        "state_data": state_data,
        "arc_beat": arc_beat,
        "sessions_in_beat": sessions_in_beat,
    }


def write_wiki_from_json(entities_json: str, session_num: int) -> tuple[int, list[str]]:
    """Parse the Wiki Keeper's JSON output and write individual entity files.

    Why: DeepSeek outputs "I'll start by..." as its final answer instead of
    calling tools. We sidestep this entirely — the Wiki Keeper just generates
    JSON (text output, no tools needed), and Python writes the files directly.

    Returns (count_written, list_of_entity_names) for the Lorekeeper to use.
    """
    import re

    # Strip markdown code fences if the LLM wrapped the JSON
    text = entities_json.strip()
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Try to find a bare JSON array anywhere in the output
        arr_match = re.search(r'\[[\s\S]*\]', text)
        if arr_match:
            text = arr_match.group()

    try:
        entities = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[Wiki] Warning: could not parse entity JSON: {e}")
        print("[Wiki] Skipping wiki update — raw output was not valid JSON.")
        return 0, []

    if not isinstance(entities, list):
        print("[Wiki] Warning: expected a JSON array, got something else. Skipping.")
        return 0, []

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    names_written = []

    for entity in entities:
        name = entity.get("name", "").strip()
        if not name:
            continue

        entity_type = entity.get("type", "unknown")
        status      = entity.get("status", "")
        location    = entity.get("location", "")
        description = entity.get("description", "")
        history     = entity.get("history", "")

        # Sanitize filename — remove characters invalid in Windows paths
        safe_name = re.sub(r'[\\/:*?"<>|]', ' ', name).strip()
        safe_name = re.sub(r'\s+', ' ', safe_name)  # collapse multiple spaces
        filename = safe_name + ".md"
        wiki_file = WIKI_DIR / filename

        if wiki_file.exists():
            # Update frontmatter fields + append a session update section.
            # We rewrite status and location if they changed (e.g. NPC died,
            # party moved to a new location) rather than leaving stale values.
            existing = wiki_file.read_text(encoding="utf-8")

            # Parse and rewrite YAML frontmatter if present
            if existing.startswith("---"):
                parts = existing.split("---", 2)  # ["", frontmatter, body]
                if len(parts) == 3:
                    fm_lines = parts[1].strip().splitlines()
                    # Update status and location lines if we have new values
                    new_fm_lines = []
                    for line in fm_lines:
                        if line.startswith("status:") and status:
                            new_fm_lines.append(f"status: {status}")
                        elif line.startswith("location:") and location:
                            new_fm_lines.append(f"location: [[{location}]]")
                        else:
                            new_fm_lines.append(line)
                    existing = "---\n" + "\n".join(new_fm_lines) + "\n---" + parts[2]

            update_block = f"## Session {session_num} Update\n\n{history}\n"
            updated = existing.rstrip() + "\n\n---\n\n" + update_block
            wiki_file.write_text(updated, encoding="utf-8")
            print(f"  [Wiki] ↻ {filename} (updated)")
        else:
            # Build full YAML frontmatter + markdown body
            fm_lines = ["---", f"type: {entity_type}"]
            if location:
                fm_lines.append(f"location: [[{location}]]")
            if status:
                fm_lines.append(f"status: {status}")
            fm_lines.append("---")
            content = "\n".join(fm_lines)
            content += f"\n# {name}\n"
            if description:
                content += f"\n**Description:** {description}\n"
            content += f"\n**First Seen:** Session {session_num}\n"
            if history:
                content += f"\n**History:** {history}\n"
            wiki_file.write_text(content, encoding="utf-8")
            print(f"  [Wiki] ✓ {filename} (created)")

        written += 1
        names_written.append(name)

    return written, names_written


def run_editor_session(
    full_transcript: str,
    session_num: int,
    blog_path,
    new_wiki_names: list,
    story_summary: str = "",
    adventure_text: str = "",
    use_claude: bool = True,
) -> list:
    """Post-session editor/fact-checker pass.

    Compares the Scribe's session report and the Wiki Keeper's new entries
    against the gameplay transcript AND the adventure file. Applies find/replace
    corrections for factual errors, flags content invention and missing content.

    Does NOT handle NPC name corrections — that stays with the Lorekeeper.
    Skips silently on JSON parse failure so it never blocks the pipeline.

    Returns a list of content_invention_flags (strings) for the Lorekeeper to use.
    """
    import re as _re

    print("[Editor] Fact-checking...")

    session_text = blog_path.read_text(encoding="utf-8")

    # Read new wiki entries written this session
    new_wiki_content = {}
    for name in new_wiki_names:
        wiki_file = WIKI_DIR / f"{name}.md"
        if wiki_file.exists():
            new_wiki_content[name] = wiki_file.read_text(encoding="utf-8")

    # Load existing wiki entries referenced in the session report
    # (filtered to links only, to keep context tight)
    linked_names = set(_re.findall(r'\[\[([^\]]+)\]\]', session_text))
    existing_wiki_content = {}
    for name in linked_names:
        wiki_file = WIKI_DIR / f"{name}.md"
        if wiki_file.exists() and name not in new_wiki_content:
            content = wiki_file.read_text(encoding="utf-8")
            # Truncate long entries — 400 chars is enough for fact-checking
            existing_wiki_content[name] = (
                content[:400] + "..." if len(content) > 400 else content
            )

    # Build string sections
    new_wiki_str = ""
    for name, content in new_wiki_content.items():
        new_wiki_str += f"\n### {name} (NEW this session)\n{content}\n"

    existing_wiki_str = ""
    for name, content in existing_wiki_content.items():
        existing_wiki_str += f"\n### {name}\n{content}\n"

    story_section = (
        f"=== CAMPAIGN STORY SO FAR ===\n{story_summary}\n\n"
        if story_summary else ""
    )

    adventure_section = ""
    if adventure_text:
        # Pass the FULL adventure file so the Editor can flag content invention
        # and check required beats. Previously truncated to 4000 chars, which
        # caused the Editor to miss inventions from later in the adventure.
        adventure_section = (
            "=== ADVENTURE FILE (THE APPROVED SOURCE MATERIAL) ===\n"
            "Everything below is what SHOULD happen in this session. Anything in the\n"
            "session report or wiki entries that is NOT in this adventure file is\n"
            "CONTENT INVENTION and must be flagged.\n\n"
            f"{adventure_text}\n\n"
        )

    prompt = (
        f"You are fact-checking Session {session_num}'s written outputs.\n\n"
        "You have TWO jobs:\n"
        "1. Check the session report and wiki entries against the GAMEPLAY TRANSCRIPT "
        "for factual errors (wrong character placement, misattributed actions).\n"
        "2. Check the session report and wiki entries against the ADVENTURE FILE "
        "for CONTENT INVENTION — creatures, NPCs, factions, plot elements, "
        "metaphysical systems, or cosmic entities that do NOT appear in the adventure "
        "file. If the adventure says the enemies are 'just rats,' but the report "
        "describes them as an organized military force with a command hierarchy, "
        "that is content invention and must be flagged.\n\n"
        "=== GAMEPLAY TRANSCRIPT (SOURCE OF TRUTH FOR EVENTS) ===\n"
        f"{full_transcript}\n\n"
        f"{adventure_section}"
        f"{story_section}"
        "=== SESSION REPORT (written by the Scribe — check for errors) ===\n"
        f"{session_text}\n\n"
        "=== NEW WIKI ENTRIES (written by Wiki Keeper — check for errors) ===\n"
        f"{new_wiki_str if new_wiki_str else 'None this session.'}\n\n"
        "=== EXISTING WIKI ENTRIES (for cross-session consistency) ===\n"
        f"{existing_wiki_str if existing_wiki_str else 'None relevant.'}\n\n"
        "YOUR TASK:\n"
        "1. Find factual errors — events that didn't happen, wrong attributions.\n"
        "2. Flag content invention — creatures, NPCs, mechanics, or plot elements "
        "that are NOT in the adventure file. List each invented element clearly.\n"
        "   COMMON INVENTIONS TO WATCH FOR:\n"
        "   - NPCs or factions that do not appear in the adventure file\n"
        "   - Enemies given speech, communication, or cooperation when the adventure\n"
        "     says they cannot speak or negotiate\n"
        "   - Boss fights or combat encounters that were SKIPPED or replaced with\n"
        "     diplomacy/cooperation when the adventure prescribes combat\n"
        "   - Metaphysical systems, cosmic entities, or magical mechanics not in\n"
        "     the adventure file\n"
        "   - The Sleeper, Deep Things, or other entities given consciousness,\n"
        "     communication, or agency beyond what the adventure describes\n"
        "3. Flag MISSING CONTENT — key beats from the adventure file that did NOT\n"
        "   appear in the session report. Check the adventure file for prescribed\n"
        "   combat encounters, puzzles, NPCs, items, and dramatic moments. If the\n"
        "   adventure says there should be a boss fight and there wasn't one, flag it.\n"
        "Keep corrections minimal — replace only the wrong phrase, not whole sentences.\n\n"
        "CRITICAL RULE FOR THE 'wrong' FIELD: You must copy the text VERBATIM from the "
        "source document — character for character, including punctuation and capitalization. "
        "Do NOT paraphrase, summarize, or reconstruct what you think the document says. "
        "Before writing a correction, find the exact sentence or phrase in the document above "
        "and copy it directly. If you cannot find the exact text to quote, skip that correction "
        "entirely. A correction with a paraphrased 'wrong' field is useless and will be ignored.\n\n"
        "OUTPUT FORMAT — output ONLY this JSON object, nothing else:\n"
        "{\n"
        '  "session_report_corrections": [\n'
        '    {"wrong": "verbatim text copied from the session report", "canonical": "corrected replacement"}\n'
        '  ],\n'
        '  "wiki_corrections": [\n'
        '    {"file": "WikiEntryName", "wrong": "verbatim text copied from that wiki file", "canonical": "corrected replacement"}\n'
        '  ],\n'
        '  "content_invention_flags": [\n'
        '    "Brief description of invented element not in adventure file"\n'
        '  ],\n'
        '  "missing_content_flags": [\n'
        '    "Brief description of adventure content that was skipped or absent from the session"\n'
        '  ]\n'
        "}\n\n"
        "If no corrections are needed, use empty arrays. "
        "CRITICAL: Output ONLY the raw JSON. No explanation, no markdown fences."
    )

    editor = create_editor(use_claude=use_claude)
    result = run_single_agent_task(
        agent=editor,
        description=prompt,
        expected_output=(
            "A JSON object with session_report_corrections and wiki_corrections arrays. "
            "Both empty if no factual errors found."
        ),
        min_words=3,  # JSON can be very short: {"session_report_corrections":[],...}
    )

    invention_flags = []

    try:
        clean = result.strip()
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean)
        if fence_match:
            clean = fence_match.group(1)
        else:
            obj_match = _re.search(r'\{[\s\S]*\}', clean)
            if obj_match:
                clean = obj_match.group()

        data = json.loads(clean)

        # Extract invention flags for downstream use (Lorekeeper)
        invention_flags = data.get("content_invention_flags", [])
        missing_flags = data.get("missing_content_flags", [])
        if invention_flags:
            print(f"[Editor] {len(invention_flags)} content invention flag(s):")
            for flag in invention_flags:
                print(f"  ⚠ {flag}")
        if missing_flags:
            print(f"[Editor] {len(missing_flags)} missing content flag(s):")
            for flag in missing_flags:
                print(f"  ✗ {flag}")

        # Apply session report corrections
        sr_corrections = data.get("session_report_corrections", [])
        if sr_corrections:
            print(f"[Editor] {len(sr_corrections)} session report correction(s):")
            text = blog_path.read_text(encoding="utf-8")
            modified = False
            for c in sr_corrections:
                wrong, canonical = c.get("wrong", ""), c.get("canonical", "")
                if wrong and canonical and wrong in text:
                    text = text.replace(wrong, canonical)
                    modified = True
                    label = wrong[:70] + "..." if len(wrong) > 70 else wrong
                    print(f"  -> corrected: '{label}'")
                elif wrong and canonical:
                    label = wrong[:70] + "..." if len(wrong) > 70 else wrong
                    print(f"  -> text not found (skipped): '{label}'")
            if modified:
                blog_path.write_text(text, encoding="utf-8")
        else:
            print("[Editor] Session report checked — no factual corrections needed.")

        # Apply wiki corrections
        wiki_corrections = data.get("wiki_corrections", [])
        if wiki_corrections:
            print(f"[Editor] {len(wiki_corrections)} wiki correction(s):")
            for c in wiki_corrections:
                file_name = c.get("file", "").strip()
                wrong, canonical = c.get("wrong", ""), c.get("canonical", "")
                if file_name and wrong and canonical:
                    wiki_file = WIKI_DIR / f"{file_name}.md"
                    if wiki_file.exists():
                        content = wiki_file.read_text(encoding="utf-8")
                        if wrong in content:
                            content = content.replace(wrong, canonical)
                            wiki_file.write_text(content, encoding="utf-8")
                            print(f"  -> [{file_name}] corrected")
                        else:
                            print(f"  -> [{file_name}] text not found (skipped)")
        else:
            print("[Editor] Wiki entries checked — no factual corrections needed.")

    except (json.JSONDecodeError, Exception) as e:
        print(f"[Editor] Warning: could not parse editor output ({e}). Skipping corrections.")

    # Always save the raw editor output as a review file for auditing
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    review_path = REVIEWS_DIR / f"session_{session_num:02d}_editor_review.md"
    review_path.write_text(
        f"# Editor Review — Session {session_num}\n\n"
        f"## Raw Editor Output\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"[Editor] Review saved to: {review_path.name}")

    return invention_flags


def run_lorekeeper_session(
    state: dict,
    session_num: int,
    blog_path,
    new_wiki_names: list,
    adventure_text: str,
    use_claude: bool = True,
    editor_invention_flags: list = None,
) -> dict:
    """Per-session Lorekeeper pass.

    Fixes NPC name drift in the session report and upgrades newly created
    wiki entries from session-log style to encyclopedic articles.
    Excludes content flagged by the Editor as invented.

    Returns the (possibly updated) state dict.
    """
    import re as _re

    print("[Lorekeeper] Consistency pass...")

    session_text = blog_path.read_text(encoding="utf-8")

    # Read only the wiki entries written this session
    new_wiki_content = {}
    for name in new_wiki_names:
        wiki_file = WIKI_DIR / f"{name}.md"
        if wiki_file.exists():
            new_wiki_content[name] = wiki_file.read_text(encoding="utf-8")

    known_npcs = state.get("known_npcs", [])
    known_npcs_str = "\n".join(f"- {n}" for n in known_npcs) if known_npcs else "None yet."

    wiki_entries_str = ""
    for name, content in new_wiki_content.items():
        wiki_entries_str += f"\n### {name}\n{content}\n"

    # Build invention flags section if the Editor flagged anything
    invention_section = ""
    if editor_invention_flags:
        flags_str = "\n".join(f"- {flag}" for flag in editor_invention_flags)
        invention_section = (
            "=== EDITOR INVENTION FLAGS (CONTENT NOT IN ADVENTURE FILE) ===\n"
            "The Editor has flagged the following as INVENTED content — things that\n"
            "appeared in the session but are NOT in the adventure file. Do NOT write\n"
            "these into wiki entries as established canon. If a wiki entry is primarily\n"
            "about an invented element, do not create or upgrade it.\n\n"
            f"{flags_str}\n\n"
        )

    prompt = (
        f"You are doing a per-session consistency pass for Session {session_num}.\n\n"
        "=== ADVENTURE FILE (CANONICAL SOURCE MATERIAL) ===\n"
        f"{adventure_text}\n\n"
        f"{invention_section}"
        "=== KNOWN NPCs FROM CAMPAIGN STATE (canonical) ===\n"
        f"{known_npcs_str}\n\n"
        "=== SESSION REPORT ===\n"
        f"{session_text}\n\n"
        "=== NEW WIKI ENTRIES TO UPGRADE ===\n"
        f"{wiki_entries_str if wiki_entries_str else 'None this session.'}\n\n"
        "YOUR TASKS:\n"
        "1. Check for NPC name inconsistencies in the session report vs the adventure "
        "file and known_npcs. If a name in the session conflicts with a canonical source, "
        "pick the canonical version. List each correction as a find/replace pair — do NOT "
        "rewrite the full session text, just list what needs changing.\n"
        "2. Rewrite each new wiki entry as a proper encyclopedic article — encyclopedic "
        "tone, organized sections, [[wiki links]] for proper nouns, NO session-log language.\n"
        "   IMPORTANT: Do NOT codify invented content as established canon. If the Editor\n"
        "   flagged something as content invention (see EDITOR INVENTION FLAGS above),\n"
        "   do not include it in wiki entries as fact. Only write content that appears in\n"
        "   the adventure file or is consistent with established campaign state.\n"
        "3. List any new named NPCs that should be added to the canonical record.\n"
        "   Only add NPCs that appear in the adventure file. Do NOT add invented NPCs.\n\n"
        "OUTPUT FORMAT — output ONLY this JSON object, nothing else:\n"
        "{\n"
        '  "corrections": [{"wrong": "BadName", "canonical": "GoodName"}],\n'
        '  "wiki_updates": [{"name": "EntryName", "content": "full wiki article"}],\n'
        '  "new_canonical_npcs": ["Name1", "Name2"]\n'
        "}\n\n"
        "If no corrections needed, corrections and new_canonical_npcs can be empty arrays. "
        "CRITICAL: Output ONLY the raw JSON. No explanation, no markdown fences."
    )

    lorekeeper = create_lorekeeper(use_claude=use_claude)
    result = run_single_agent_task(
        agent=lorekeeper,
        description=prompt,
        expected_output=(
            "A JSON object with corrected_session, corrections, wiki_updates, "
            "and new_canonical_npcs fields."
        ),
    )

    try:
        clean = result.strip()
        # Strip markdown fences if present
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean)
        if fence_match:
            clean = fence_match.group(1)
        else:
            obj_match = _re.search(r'\{[\s\S]*\}', clean)
            if obj_match:
                clean = obj_match.group()

        data = json.loads(clean)

        # 1. Apply corrections to session report and ALL wiki files via find/replace
        corrections = data.get("corrections", [])
        if corrections:
            print(f"[Lorekeeper] {len(corrections)} name correction(s): "
                  + ", ".join(f"{c['wrong']} → {c['canonical']}" for c in corrections))
            # Apply to session report
            session_text_current = blog_path.read_text(encoding="utf-8")
            modified = False
            for c in corrections:
                wrong, canonical = c.get("wrong", ""), c.get("canonical", "")
                if wrong and canonical and wrong in session_text_current:
                    session_text_current = session_text_current.replace(wrong, canonical)
                    modified = True
            if modified:
                blog_path.write_text(session_text_current, encoding="utf-8")
            # Propagate corrections to ALL wiki files
            for wiki_file in WIKI_DIR.glob("*.md"):
                content = wiki_file.read_text(encoding="utf-8")
                wiki_modified = False
                for c in corrections:
                    wrong, canonical = c.get("wrong", ""), c.get("canonical", "")
                    if wrong and canonical and wrong in content:
                        content = content.replace(wrong, canonical)
                        wiki_modified = True
                if wiki_modified:
                    wiki_file.write_text(content, encoding="utf-8")
        else:
            print("[Lorekeeper] Session report checked — no name corrections needed.")

        # 2. Write upgraded wiki entries
        wiki_updates = data.get("wiki_updates", [])
        for update in wiki_updates:
            name = update.get("name", "").strip()
            content = update.get("content", "").strip()
            if name and content:
                wiki_file = WIKI_DIR / f"{name}.md"
                wiki_file.write_text(content, encoding="utf-8")
        if wiki_updates:
            print(f"[Lorekeeper] Upgraded {len(wiki_updates)} wiki entry/entries to encyclopedic format.")

        # 3. Add new canonical NPCs to state
        new_npcs = data.get("new_canonical_npcs", [])
        if new_npcs:
            existing = state.get("known_npcs", [])
            added = []
            for npc in new_npcs:
                if npc not in existing:
                    existing.append(npc)
                    added.append(npc)
            state["known_npcs"] = existing
            save_state(state)
            if added:
                print(f"[Lorekeeper] Added to canonical record: {', '.join(added)}")

    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Lorekeeper] Could not parse output ({e}) — skipping this pass.")

    # Always save the raw lorekeeper output as a review file for auditing
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    review_path = REVIEWS_DIR / f"session_{session_num:02d}_lore_review.md"
    review_path.write_text(
        f"# Lorekeeper Review — Session {session_num}\n\n"
        f"## Raw Lorekeeper Output\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"[Lorekeeper] Review saved to: {review_path.name}")

    print()
    return state


def run_lorekeeper_adventure(state: dict, use_claude: bool = True) -> None:
    """End-of-adventure Lorekeeper pass.

    Full editorial pass on all wiki entries: rewrites to encyclopedic format,
    merges duplicates, ensures cross-references are consistent.
    Processes in batches of 25 to stay within token limits.
    """
    import re as _re

    print("[Lorekeeper] Running end-of-adventure wiki editorial pass...\n")

    wiki_files = sorted(WIKI_DIR.glob("*.md"))
    if not wiki_files:
        print("[Lorekeeper] No wiki entries found — skipping.\n")
        return

    # Read all entries
    all_entries = {f.stem: f.read_text(encoding="utf-8") for f in wiki_files}
    print(f"[Lorekeeper] Processing {len(all_entries)} wiki entries in batches...\n")

    lorekeeper = create_lorekeeper(use_claude=use_claude)
    BATCH_SIZE = 25
    entry_items = list(all_entries.items())
    to_delete = []

    for batch_start in range(0, len(entry_items), BATCH_SIZE):
        batch = entry_items[batch_start: batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(entry_items) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[Lorekeeper] Batch {batch_num}/{total_batches} ({len(batch)} entries)...")

        wiki_str = ""
        for name, content in batch:
            wiki_str += f"\n---\n### {name}\n{content}\n"

        # Include all entry names so cross-references are accurate
        all_names = list(all_entries.keys())
        names_list = ", ".join(f"[[{n}]]" for n in all_names)

        prompt = (
            "You are doing a full editorial pass on a batch of campaign wiki entries.\n\n"
            f"ALL KNOWN WIKI ENTRY NAMES (for cross-references):\n{names_list}\n\n"
            "=== WIKI ENTRIES TO EDIT ===\n"
            f"{wiki_str}\n\n"
            "YOUR TASKS FOR EACH ENTRY:\n"
            "1. Rewrite as a proper encyclopedic article:\n"
            "   - Third person, present tense for living subjects\n"
            "   - Clear opening sentence defining the subject\n"
            "   - Organized sections with ## headers where appropriate\n"
            "   - [[wiki links]] for proper nouns on first mention per section\n"
            "   - No session-log language ('in session 2...', 'the party found...')\n"
            "2. If two entries in this batch are clearly the same subject with different "
            "names (e.g. 'Aldric' and 'Warden Aldric'), merge them into one entry using "
            "the more complete name, and add the shorter name to the delete list.\n\n"
            "OUTPUT FORMAT — output ONLY this JSON, nothing else:\n"
            "{\n"
            '  "updates": [{"name": "EntryName", "content": "full article text"}],\n'
            '  "delete": ["DuplicateNameToRemove"]\n'
            "}\n\n"
            "Include ALL entries from this batch in updates (even unchanged ones). "
            "CRITICAL: Output ONLY the raw JSON. No explanation, no markdown fences."
        )

        result = run_single_agent_task(
            agent=lorekeeper,
            description=prompt,
            expected_output=(
                "A JSON object with updates (list of name+content pairs for all "
                "entries in the batch) and delete (list of duplicate filenames to remove)."
            ),
        )

        try:
            clean = result.strip()
            fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean)
            if fence_match:
                clean = fence_match.group(1)
            else:
                obj_match = _re.search(r'\{[\s\S]*\}', clean)
                if obj_match:
                    clean = obj_match.group()

            data = json.loads(clean)

            updates = data.get("updates", [])
            for update in updates:
                name = update.get("name", "").strip()
                content = update.get("content", "").strip()
                if name and content:
                    wiki_file = WIKI_DIR / f"{name}.md"
                    wiki_file.write_text(content, encoding="utf-8")

            batch_deletes = data.get("delete", [])
            to_delete.extend(batch_deletes)
            print(f"[Lorekeeper] Batch {batch_num}: {len(updates)} updated, "
                  f"{len(batch_deletes)} marked for deletion.")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[Lorekeeper] Batch {batch_num} parse error ({e}) — skipping batch.")

    # Remove duplicates flagged by the editorial batches
    if to_delete:
        for name in to_delete:
            wiki_file = WIKI_DIR / f"{name}.md"
            if wiki_file.exists():
                wiki_file.unlink()
        print(f"[Lorekeeper] Removed {len(to_delete)} duplicate(s): {', '.join(to_delete)}")

    # --- Dedicated cross-batch dedup pass ---
    # Reload entries after editorial pass (content may have changed)
    wiki_files_post = sorted(WIKI_DIR.glob("*.md"))
    all_entries_post = {f.stem: f.read_text(encoding="utf-8") for f in wiki_files_post}

    # Build a compact summary: name + first sentence only
    summaries = []
    for name, content in all_entries_post.items():
        first_sentence = content.split(".")[0].strip() if content else ""
        summaries.append(f"{name}: {first_sentence}.")

    summary_str = "\n".join(summaries)

    dedup_prompt = (
        "You are reviewing a campaign wiki for duplicate entries that describe the same "
        "real-world subject under different names.\n\n"
        "Below is every wiki entry with its name and opening sentence:\n\n"
        f"{summary_str}\n\n"
        "Identify ANY pairs where both entries clearly describe the same subject "
        "(e.g. 'Laternian Academy' and 'University of Laternian' are the same institution, "
        "or 'Warden Aldric' and 'Aldric' are the same person). "
        "For each duplicate pair, choose which name to KEEP (the more complete/specific one) "
        "and which name to DELETE. The kept entry already contains merged information.\n\n"
        "OUTPUT FORMAT — output ONLY this JSON, nothing else:\n"
        '{"duplicates": [{"keep": "FullName", "delete": "ShortOrAltName"}]}\n\n'
        "If no duplicates exist, output: {\"duplicates\": []}\n"
        "CRITICAL: Output ONLY the raw JSON. No explanation, no markdown fences."
    )

    print("[Lorekeeper] Running cross-batch dedup pass...")
    dedup_result = run_single_agent_task(
        agent=lorekeeper,
        description=dedup_prompt,
        expected_output='JSON with "duplicates" list of keep/delete pairs.',
    )

    try:
        clean_dedup = dedup_result.strip()
        fence_match_d = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean_dedup)
        if fence_match_d:
            clean_dedup = fence_match_d.group(1)
        else:
            obj_match_d = _re.search(r'\{[\s\S]*\}', clean_dedup)
            if obj_match_d:
                clean_dedup = obj_match_d.group()

        dedup_data = json.loads(clean_dedup)
        duplicates = dedup_data.get("duplicates", [])
        if duplicates:
            for pair in duplicates:
                keep = pair.get("keep", "").strip()
                delete = pair.get("delete", "").strip()
                if keep and delete:
                    delete_file = WIKI_DIR / f"{delete}.md"
                    keep_file = WIKI_DIR / f"{keep}.md"
                    if delete_file.exists() and keep_file.exists():
                        delete_file.unlink()
                        print(f"[Lorekeeper] Merged duplicate: '{delete}' → '{keep}' (deleted '{delete}')")
            print(f"[Lorekeeper] Dedup pass: {len(duplicates)} duplicate(s) resolved.")
        else:
            print("[Lorekeeper] Dedup pass: no duplicates found.")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Lorekeeper] Dedup pass parse error ({e}) — skipping.")

    print(f"[Lorekeeper] End-of-adventure editorial pass complete.\n")


def _run_enemy_turn(enemy_agents: dict, rules_keeper,
                    dm_narration: str, pc_actions: str,
                    combat_active: bool, transcript: list) -> tuple[str, str]:
    """Run all enemy agents for one round and adjudicate their actions.

    Group E: Enemy agents declare their own combat actions independently
    from the DM. The Rules Keeper adjudicates enemy actions the same way
    it adjudicates PC actions. Returns (combined_enemy_actions, enemy_rulings).

    Args:
        enemy_agents: Dict of {"leader": {...}, "swarm": {...}} with agent and config
        rules_keeper: The Rules Keeper agent
        dm_narration: The DM's most recent narration
        pc_actions: Combined PC actions (empty if enemies go first)
        combat_active: Whether combat has already been triggered
        transcript: The session transcript list to append to

    Returns:
        Tuple of (combined_enemy_actions, enemy_rulings) — both empty strings
        if no enemy actions were produced.
    """
    all_enemy_actions = []

    for role, entry in enemy_agents.items():
        agent = entry["agent"]
        cfg = entry["config"]
        name = cfg["name"]

        enemy_description = (
            f"You are {name} in active combat.\n\n"
            "The DM has narrated the following scene:\n\n"
            f"---\n{dm_narration}\n---\n\n"
        )

        if pc_actions:
            enemy_description += (
                "The player characters have acted:\n\n"
                f"---\n{pc_actions}\n---\n\n"
            )

        enemy_description += (
            "It is YOUR turn. Declare your combat actions for this round. "
            "Use the Roll Dice tool for attack rolls and damage rolls. "
            "Follow your behavioral triggers exactly. Pick targets based on "
            "your combat behavior rules.\n\n"
            "Output your actions in this format:\n"
            f"=== {name.upper()} ACTIONS ===\n"
            "ACTION: [Attack] targeting [target]. [Roll dice]\n"
            "BONUS ACTION: [If applicable]\n"
            "LEGENDARY ACTION: [If applicable]"
        )

        print(f"\n[Enemy] {name} acting...\n")
        enemy_response = run_single_agent_task(
            agent=agent,
            description=enemy_description,
            expected_output=(
                f"Combat actions for {name} including attack rolls and targets."
            ),
            min_words=5,
        )

        print(f"\n--- {name} (Enemy) ---\n{enemy_response}\n")
        all_enemy_actions.append(f"**{name}**: {enemy_response}")
        transcript.append(f"### {name} (Enemy)\n\n{enemy_response}")

    if not all_enemy_actions:
        return "", ""

    combined_enemy_actions = "\n\n".join(all_enemy_actions)

    # Rules Keeper adjudicates enemy actions
    enemy_rules_description = (
        "The following ENEMY CREATURES have declared their combat actions:\n\n"
        f"---\n{combined_enemy_actions}\n---\n\n"
        "The current scene:\n\n"
        f"---\n{dm_narration}\n---\n\n"
        "Adjudicate the enemy actions above using D&D 5e rules. For each "
        "attack, compare the roll to the target's AC. For each save, compare "
        "to the appropriate DC. Calculate damage on hits. Track which PCs "
        "take damage and any conditions applied.\n\n"
        "Use the 'Load Campaign State' tool if you need to check party stats."
    )

    enemy_rulings = run_single_agent_task(
        agent=rules_keeper,
        description=enemy_rules_description,
        expected_output=(
            "Rules adjudication for enemy actions:\n"
            "=== RULES KEEPER (ENEMY ACTIONS) ===\n"
            "[Enemy]: [Attack] vs [Target] — [Roll] vs [AC/DC] — **[RESULT]** "
            "[damage/effect]"
        ),
        min_words=5,
    )

    print(f"\n--- Rules Keeper (Enemy) ---\n{enemy_rulings}\n")
    transcript.append(f"### Rules Keeper (Enemy Actions)\n\n{enemy_rulings}")

    return combined_enemy_actions, enemy_rulings


def run_session(dm_use_claude: bool = True, dry_run: bool = False,
                all_deepseek: bool = False):
    """Run a full D&D session.

    This is the main game loop. Here's what happens:

    1. SETUP: Load state, create agents, read world context
    2. OPENING: DM sets the scene based on adventure + world files
    3. GAME LOOP: For each exchange...
       a. DM narrates (checks for human DM input too)
       b. Each PC responds in character
       c. If dice rolls or rules questions arise, adjudicate
       d. Build up the session transcript
    4. WRAP-UP: DM narrates a closing scene
    5. SCRIBE: Write the session blog
    6. WIKI: Update the wiki with new discoveries
    7. SAVE: Persist campaign state

    Args:
        dm_use_claude: True to use Claude for the DM, False for DeepSeek
        dry_run: True to limit to 3 exchanges for testing
        all_deepseek: True to use DeepSeek for ALL agents (overrides dm_use_claude)
    """
    max_exchanges = DRY_RUN_EXCHANGES if dry_run else DEFAULT_EXCHANGES

    # If all_deepseek is set, override dm_use_claude
    if all_deepseek:
        dm_use_claude = False
    # Scribe and Wiki use Claude unless all_deepseek is set
    creative_use_claude = not all_deepseek

    # --- Reset API call counter ---
    global _api_call_count
    _api_call_count = 0

    # --- Load state and increment session number ---
    state = load_state()
    state["session_number"] = state.get("session_number", 0) + 1
    session_num = state["session_number"]

    # --- Pre-seed wiki on first session of a fresh campaign ---
    if session_num == 1:
        import pathlib
        seed_dir = pathlib.Path("wiki_seed")
        if seed_dir.exists():
            seed_files = list(seed_dir.glob("*.md"))
            if seed_files:
                wiki_dir = pathlib.Path("output/wiki")
                wiki_dir.mkdir(parents=True, exist_ok=True)
                for seed_file in seed_files:
                    dest = wiki_dir / seed_file.name
                    if not dest.exists():
                        dest.write_text(seed_file.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"[Wiki] Pre-seeded {len(seed_files)} canonical wiki entries from wiki_seed/")

    # --- Capture Python-authoritative values before DM can touch them ---
    # Party levels are managed by Python's level_up_party(); DM must not change them.
    # Guard: the DM sometimes writes party as a flat object (members/hp/inventory keys)
    # instead of the expected {name: {level, hp, conditions}} structure. If that happens,
    # rebuild the party dict from the known PC names to avoid a crash.
    PC_NAMES = ["Cora Flint", "Garrick Kade", "Professor Thaddeus Mercer"]
    raw_party = state.get("party", {})
    if not isinstance(raw_party, dict) or not any(k in raw_party for k in PC_NAMES):
        print("[State] Warning: party structure was malformed — rebuilding from PC names.")
        existing = raw_party if isinstance(raw_party, dict) else {}
        state["party"] = {
            name: {"level": existing.get(name, {}).get("level", 1)
                   if isinstance(existing.get(name), dict) else 1,
                   "hp": "full", "conditions": ""}
            for name in PC_NAMES
        }
    party_levels = {
        name: data.get("level", 1)
        for name, data in state["party"].items()
        if isinstance(data, dict)
    }

    # --- Track adventure progress ---
    state["sessions_in_adventure"] = state.get("sessions_in_adventure", 0) + 1
    adventure_num = state.get("current_adventure", 1)
    # Derive adventure name from the current adventure file if not yet in state
    if not state.get("current_adventure_name") or state.get("current_adventure_name") == "Unknown":
        try:
            adv_first_line = CURRENT_ADVENTURE.read_text(encoding="utf-8").splitlines()[0]
            # First line is e.g. "# Adventure 1: The Desperate Bounty (Level 1)"
            adv_name_match = re.search(r'Adventure \d+:\s*(.+?)(?:\s*\(|$)', adv_first_line)
            if adv_name_match:
                state["current_adventure_name"] = adv_name_match.group(1).strip()
        except Exception:
            pass
    adventure_name = state.get("current_adventure_name", "Unknown")
    adventure_session = state["sessions_in_adventure"]
    max_adventure_sessions = state.get("max_sessions_per_adventure", 3)

    model_label = "All DeepSeek" if all_deepseek else (
        "Claude DM" if dm_use_claude else "DeepSeek DM + Claude Scribe/Wiki"
    )
    print(f"\n{'='*60}")
    print(f"  SESSION {session_num} BEGINNING")
    print(f"  Adventure {adventure_num}: {adventure_name}")
    print(f"  Adventure Session: {adventure_session}/{max_adventure_sessions}")
    print(f"  Models: {model_label}")
    print(f"  Exchanges: {max_exchanges} ({'dry run' if dry_run else 'full session'})")
    print(f"{'='*60}\n")

    # --- Create all agents ---
    dm = create_dm_agent(use_claude=dm_use_claude)
    pcs = create_pc_agents(party_state=state.get("party", {}))
    rules_keeper = create_rules_keeper()
    scribe = create_scribe(use_claude=creative_use_claude)
    wiki_keeper = create_wiki_keeper(use_claude=creative_use_claude)

    pc_names = ["Cora Flint", "Garrick Kade", "Professor Thaddeus Mercer"]

    # --- Group E: Create enemy agents if this adventure has a combat encounter ---
    encounter_config = get_encounter(adventure_num)
    enemy_agents = {}  # key: "leader" or "swarm", value: Agent
    enemy_goes_first = False
    if encounter_config:
        for role in ("leader", "swarm"):
            cfg = encounter_config.get(role)
            if cfg:
                agent = create_enemy_agent(
                    name=cfg["name"],
                    tier=cfg["tier"],
                    behavior=cfg["behavior"],
                    stat_block=cfg["stat_block"],
                    phase_info=cfg.get("phase_info", ""),
                )
                enemy_agents[role] = {"agent": agent, "config": cfg}
                # If any enemy is hostile_only, enemies go first
                if cfg.get("hostile_only", False):
                    enemy_goes_first = True
        agent_names = [c["config"]["name"] for c in enemy_agents.values()]
        print(f"[Session] Enemy agents created: {', '.join(agent_names)}")
        print(f"[Session] Enemy acts {'FIRST' if enemy_goes_first else 'AFTER PCs'} "
              f"({'HOSTILE-ONLY' if enemy_goes_first else 'PC-initiated'})")
    combat_active = False  # Tracks whether combat has started this session

    # Signals that combat has ended — checked in enemy_actions, enemy_rulings, and dm_narration
    # Use specific phrases to avoid false positives (e.g., "defeated" in backstory narration)
    COMBAT_END_SIGNALS = [
        "COMBAT ENDS", "COMBAT HAS ENDED", "COMBAT IS OVER",
        "NO ENEMY ACTIONS", "NO ACTIVE ENEMIES", "ENCOUNTER IS CONCLUDED",
        "IS DEAD. NO ATTACK", "IS DEAD. NO ACTIONS", "IS DEAD AND",
        "I AM DEAD", "I HAVE BEEN DESTROYED", "I HAVE BEEN DEFEATED",
        "NO LONGER A THREAT", "NO LONGER A COMBAT THREAT",
        "HAS BEEN DEFEATED", "HAS BEEN DESTROYED", "HAS BEEN KILLED",
        "HAS BEEN SLAIN", "FALLS DEAD", "LIES DEAD",
        "NO ACTIONS THIS ROUND", "NO COMBAT ACTIONS",
        "TAKES NO ACTIONS", "TAKES NO COMBAT ACTIONS",
        "NO VALID TARGETS", "NOT WITHIN RANGE", "OUT OF RANGE",
        "CANNOT REACH", "NOT IN RANGE", "NO ATTACK POSSIBLE",
    ]
    # Keywords that indicate an enemy agent made a real attack (not just "no targets")
    REAL_ATTACK_KEYWORDS = [
        "TO HIT", "DAMAGE", "ATTACK ROLL", "ROLLED", "VS AC",
        "BITE", "SLAM", "CHARGE", "STRIKE", "WARHAMMER",
        "DRILL", "PULSE", "BURST", "WAVE", "GAZE", "GRASP",
        "HITS", "MISSES", "DEALS", "TAKES",
    ]
    # Track how many exchanges combat has been active (don't end combat on exchange 1)
    combat_exchanges = 0
    # Track whether any enemy agent has actually attacked (not just declared "no targets").
    # Combat-end detection is suppressed until this is True. Fixes pre-combat false
    # triggers where enemy agents report "no valid targets" before combat starts
    # (Run 8 S4 Amalgamation, Run 8 S12 Sentinel).
    enemy_has_attacked = False
    # Track consecutive exchanges where enemy agent produced no actual attacks
    # (e.g., "no valid targets" / "out of range"). Clear combat after 2+ consecutive.
    no_attack_exchanges = 0

    def _has_real_attack(text: str) -> bool:
        """Check if text contains evidence of a real enemy attack."""
        if not text:
            return False
        upper = text.upper()
        return any(kw in upper for kw in REAL_ATTACK_KEYWORDS)

    def _check_combat_ended(*texts: str) -> bool:
        """Check if any of the provided texts contain combat-ending signals.
        Only triggers after at least 2 exchanges of combat AND after the enemy
        has actually attacked at least once. This prevents pre-combat false
        triggers where the enemy agent says 'no valid targets' before combat
        has really started."""
        if combat_exchanges < 2:
            return False
        if not enemy_has_attacked:
            return False
        for text in texts:
            if text:
                upper = text.upper()
                for signal in COMBAT_END_SIGNALS:
                    if signal in upper:
                        return True
        return False

    # --- Build the full transcript as we go ---
    transcript: list[str] = []

    # --- OPENING SCENE ---
    # Pre-load all context in Python so DeepSeek doesn't need to call tools
    # (DeepSeek sometimes outputs "I'll gather context..." as its final answer
    # instead of actually narrating — injecting context directly fixes this)
    print("\n[DM] Opening scene...\n")
    dm_ctx = preload_dm_context()

    # Extract only the current session's section from the adventure file.
    # Giving DeepSeek the full adventure file causes it to read future session
    # content (Session 3's dungeon reveal) and skip ahead to it in Session 1.
    # Python strips out all future session sections before injecting the text.
    dm_adventure_text = extract_session_section(dm_ctx["adventure"], adventure_session)

    # --- Group D: Detect HOSTILE-ONLY boss encounters ---
    import re as _hostile_re
    _hostile_match = _hostile_re.search(
        r'\*\*HOSTILE-ONLY ENCOUNTER[^*]*\*\*',
        dm_adventure_text,
        _hostile_re.IGNORECASE
    )
    has_hostile_encounter = bool(_hostile_match)
    if has_hostile_encounter:
        print(f"[Session] HOSTILE-ONLY encounter detected in adventure file. "
              f"Auto-initiative and combat forcing ACTIVE.")

    dm_input_section = (
        f"\n\nSPECIAL INSTRUCTIONS FROM THE HUMAN DM:\n{dm_ctx['dm_input']}"
        if dm_ctx["dm_input"] else ""
    )

    # Campaign arc — DO NOT inject into DM prompt.
    # The arc lists all 20 adventures by name and description, and DeepSeek
    # latches onto future adventure content (e.g. "Salt-Vaults") instead of
    # following the current adventure file. The adventure file already contains
    # everything the DM needs for the current session.
    arc_section = ""

    # Beat escalation nudge — Python decides based on sessions_in_beat counter.
    # After 3 sessions in the same beat, the story needs a turning point.
    sessions_in_beat = dm_ctx["sessions_in_beat"]
    arc_beat = dm_ctx["arc_beat"]
    if arc_beat and sessions_in_beat >= 3:
        beat_section = (
            f"\n\nNARRATIVE ESCALATION REQUIRED: The story has been in the same "
            f"beat for {sessions_in_beat} sessions without advancing. This session "
            f"MUST push to the next story beat: '{arc_beat}'. Force a turning point "
            f"— an ambush, a revelation, a deadline, a betrayal. Something must "
            f"change dramatically. The players need a reason to act NOW."
        )
    elif arc_beat:
        beat_section = (
            f"\n\nCURRENT NARRATIVE BEAT: {arc_beat}\n"
            "Keep this goal in mind as you narrate. Push events in this direction."
        )
    else:
        beat_section = ""

    # Rest/resupply section — triggers at the start of a new adventure (not the first)
    # This fixes the test-run problem where the party went 6+ sessions with no rest.
    if adventure_session == 1 and adventure_num > 1:
        rest_section = (
            "\n\n=== REST & RESUPPLY (MANDATORY) ===\n"
            "This is the FIRST session of a new adventure. Before the new adventure "
            "begins, narrate a brief downtime period:\n"
            "- The party has completed a long rest. ALL hit points and spell slots "
            "are restored to full. Hit dice are recovered (half total, rounded down).\n"
            "- The party has had time to resupply in Grimhold or from their base. "
            "Basic supplies (rations, ammunition, common materials) are restocked.\n"
            "- Any non-magical injuries or minor conditions from the previous adventure "
            "have healed during the downtime.\n"
            "- Narrate this as a brief transition (1-2 paragraphs): a few days of rest, "
            "a trip to Grimhold for supplies, conversations between characters about what "
            "comes next. Then move into the new adventure's opening.\n"
            "- The party state below may show damage from the previous adventure. "
            "IGNORE those HP values — everyone starts this adventure at full health.\n"
        )
    else:
        rest_section = ""

    opening_description = (
        f"You are the Dungeon Master starting SESSION {session_num} of the campaign. "
        "All the context you need is provided below — you do NOT need to call any tools. "
        "Your ONLY job right now is to write the opening narration.\n\n"
        f"=== CRITICAL PACING RULES (SESSION {adventure_session} OF {max_adventure_sessions}) ===\n"
        f"You are running SESSION {adventure_session} of this adventure.\n"
        f"- ONLY use content from the 'Session {adventure_session}' section of the adventure file.\n"
        f"- Do NOT use content from any other session section. Content from Session "
        f"{adventure_session + 1 if adventure_session < max_adventure_sessions else adventure_session} "
        f"and beyond is FORBIDDEN — it has not happened yet.\n"
        "- Do NOT compress the adventure. This session covers ONE section only.\n"
        "- Do NOT skip travel, exploration, or NPC interactions to rush to the climax.\n"
        "- A session should feel like a chapter of a book — one location, one set of "
        "challenges, one dramatic question. Not a summary of the whole story.\n"
        "- NEVER have the party travel to a major new location AND resolve what they "
        "find there in the same session.\n"
        "- Only use events, NPCs, and locations described in the adventure file for "
        f"Session {adventure_session}. Do not invent major plot elements (rituals, "
        "convergences, awakenings, non-human entities) that are not in the source material.\n"
        "- Named NPCs in the adventure file MUST be used with their exact names as written. "
        "Do NOT rename, substitute, or invent alternative names for any character named in "
        "the adventure script. If the adventure file calls a character 'Aldric', you call "
        "them 'Aldric' — never 'Valerius' or any other substitution.\n"
        f"- The session MUST end at the 'Session {adventure_session} Ends When' marker "
        "in the adventure file. Do NOT go past that point.\n\n"
        "=== CAMPAIGN WORLD ===\n"
        f"{dm_ctx['world']}\n\n"
        "=== CURRENT ADVENTURE (THIS IS YOUR SCRIPT — FOLLOW IT EXACTLY) ===\n"
        "ALL session content MUST come from this adventure file. Do NOT invent "
        "locations, factions, creatures, or plot elements not described here.\n\n"
        f"{dm_adventure_text}\n\n"
        "=== PARTY STATE ===\n"
        f"{dm_ctx['state']}\n\n"
        f"=== WHERE THE STORY IS RIGHT NOW ===\n"
        f"Current location: {dm_ctx.get('state_data', {}).get('current_location', 'Unknown')}\n"
        f"Story so far: {dm_ctx.get('state_data', {}).get('story_summary', '(Campaign has just begun — nothing has happened yet.)')}\n"
        "The session MUST begin at the current location above. "
        "Do NOT assume any events have occurred that are not in the story summary. "
        "If the story summary is empty, this is Session 1 of the entire campaign — start fresh.\n"
        f"{rest_section}"
        f"{beat_section}"
        f"{dm_input_section}\n\n"
        "=== YOUR TASK ===\n"
        f"Write the opening narration for Session {session_num} "
        f"(Adventure Session {adventure_session} of {max_adventure_sessions}). "
        f"Use ONLY the 'Session {adventure_session}' section of the adventure file. "
        "If this is Session 1 of the adventure, introduce the setting vividly and "
        "present the adventure hook. "
        "If this is a later session, briefly recap where we left off, then continue the story. "
        "End your narration with a clear, active situation that forces the player characters "
        f"to make decisions or take action right now. Do NOT advance past the "
        f"'Session {adventure_session} Ends When' marker."
    )

    dm_narration = run_single_agent_task(
        agent=dm,
        description=opening_description,
        expected_output=(
            "A vivid, atmospheric opening narration (2-4 paragraphs) that sets "
            "the scene and presents the characters with a situation requiring action."
        ),
    )

    print(f"\n--- DM ---\n{dm_narration}\n")
    transcript.append(f"## DM (Opening)\n\n{dm_narration}")

    # --- MAIN GAME LOOP ---
    for exchange_num in range(1, max_exchanges + 1):
        print(f"\n{'─'*40}")
        print(f"  Exchange {exchange_num}/{max_exchanges}")
        if combat_active:
            print(f"  ⚔ COMBAT ACTIVE")
            combat_exchanges += 1
        print(f"{'─'*40}\n")

        # =====================================================================
        # Group E: Enemy agents act BEFORE PCs for HOSTILE-ONLY encounters,
        # AFTER PCs for PC-initiated combat. Non-combat exchanges skip enemies.
        # =====================================================================

        enemy_actions = ""
        enemy_rulings = ""

        # --- ENEMY ACTS FIRST (HOSTILE-ONLY, before PCs) ---
        if enemy_agents and enemy_goes_first and (combat_active or has_hostile_encounter):
            enemy_actions, enemy_rulings = _run_enemy_turn(
                enemy_agents, rules_keeper, dm_narration, "", combat_active, transcript
            )
            if enemy_actions:
                combat_active = True
            # Track whether enemy has actually attacked (vs just "no valid targets")
            if combat_active and enemy_actions:
                if _has_real_attack(enemy_actions):
                    enemy_has_attacked = True
                    no_attack_exchanges = 0
                else:
                    no_attack_exchanges += 1
                    # Only end combat for no-attacks if enemy has attacked before
                    # (pre-combat "no valid targets" should not end combat)
                    if enemy_has_attacked and no_attack_exchanges >= 2:
                        combat_active = False
                        print(f"[Session] Combat ended — no actual attacks for {no_attack_exchanges} "
                              f"consecutive exchanges (enemy-first path, exchange {exchange_num})")
                    elif not enemy_has_attacked and no_attack_exchanges >= 3:
                        # Enemy never attacked after 3 exchanges — likely false trigger,
                        # deactivate combat silently
                        combat_active = False
                        combat_exchanges = 0
                        no_attack_exchanges = 0
                        print(f"[Session] Combat deactivated — enemy never attacked after "
                              f"{no_attack_exchanges} exchanges (false trigger, exchange {exchange_num})")
            # Detect combat ending from enemy actions or rulings
            # (_check_combat_ended already requires enemy_has_attacked)
            if _check_combat_ended(enemy_actions, enemy_rulings):
                combat_active = False
                print(f"[Session] Combat ended — enemy defeated (enemy-first path, exchange {exchange_num})")

        # --- Each PC responds to the DM's narration (+ enemy actions if any) ---
        pc_responses = []
        for i, (pc, name) in enumerate(zip(pcs, pc_names)):

            pc_description = (
                "The Dungeon Master has narrated the following:\n\n"
                f"---\n{dm_narration}\n---\n\n"
            )

            # If enemies acted first, PCs see what happened
            if enemy_actions:
                pc_description += (
                    "ENEMY ACTIONS THIS ROUND (already happened before your turn):\n\n"
                    f"---\n{enemy_actions}\n---\n\n"
                    "RULES KEEPER ADJUDICATION OF ENEMY ACTIONS:\n\n"
                    f"---\n{enemy_rulings}\n---\n\n"
                )

            pc_description += (
                "Respond IN CHARACTER. Describe what you do, say any dialogue "
                "(in quotes), and explain your reasoning briefly. If you need to "
                "make an ability check, saving throw, or attack roll, use the "
                "'Roll Dice' tool with the appropriate notation (e.g., '1d20+5' "
                "for a skill check). State what the roll is for.\n\n"
                "Also consider what the other party members are doing. "
                "You can react to their actions or suggest plans."
            )

            # --- Group D: Garrick combat override for HOSTILE-ONLY encounters ---
            if has_hostile_encounter and name == "Garrick Kade":
                pc_description += (
                    "\n\nCOMBAT OVERRIDE: This adventure has a HOSTILE-ONLY boss "
                    "encounter. If the DM describes ANY threatening creature, entity, "
                    "or construct, your response MUST include attacking it. Do not "
                    "wait, do not observe, do not suggest alternatives. Attack first."
                )

            # After the first PC, include previous PCs' responses for context
            if pc_responses:
                other_responses = "\n\n".join(
                    f"**{pc_names[j]}** said/did: {resp}"
                    for j, resp in enumerate(pc_responses)
                )
                pc_description += (
                    f"\n\nYour party members have already acted:\n{other_responses}"
                )

            response = run_single_agent_task(
                agent=pc,
                description=pc_description,
                expected_output=(
                    "An in-character response (1-3 paragraphs) describing your "
                    "actions, dialogue, and any dice rolls with results."
                ),
            )

            print(f"\n--- {name} ---\n{response}\n")
            pc_responses.append(response)
            transcript.append(f"### {name}\n\n{response}")

        # --- Combine PC responses for the Rules Keeper and DM ---
        combined_pc_actions = "\n\n".join(
            f"**{name}**: {resp}"
            for name, resp in zip(pc_names, pc_responses)
        )

        # --- Rules Keeper adjudicates PC actions ---
        rules_description = (
            "The DM narrated the following scene:\n\n"
            f"---\n{dm_narration}\n---\n\n"
            "The player characters responded with:\n\n"
            f"---\n{combined_pc_actions}\n---\n\n"
            "Review the PC actions above. For any dice rolls, ability checks, "
            "attack rolls, saving throws, or contested actions, adjudicate them "
            "using D&D 5e rules with a rule-of-cool philosophy. If no rolls or "
            "contested actions occurred, simply state 'No contested actions this round.'\n\n"
            "Use the 'Load Campaign State' tool if you need to check party stats."
        )

        # --- Group D: Auto-initiative for HOSTILE-ONLY encounters ---
        if has_hostile_encounter and not combat_active:
            rules_description += (
                "\n\nCOMBAT TRIGGER RULE: This adventure contains a HOSTILE-ONLY "
                "boss encounter. When the DM narration describes the party "
                "encountering, seeing, or being in the presence of a boss creature "
                "or hostile entity from the adventure's stat block, you MUST:\n"
                "1. Declare 'INITIATIVE TRIGGERED' and roll 1d20 for each party "
                "member and for the boss creature using the Roll Dice tool\n"
                "2. List the initiative order\n"
                "3. State: 'Combat has begun. The boss attacks on its turn.'\n"
                "This overrides all other adjudication. If a boss creature is "
                "present in the scene and no initiative has been rolled, roll it NOW."
            )

        rulings = run_single_agent_task(
            agent=rules_keeper,
            description=rules_description,
            expected_output=(
                "A brief rules adjudication in the format:\n"
                "=== RULES KEEPER ===\n"
                "[Character]: [Action] — [Roll] vs [DC/AC] — **[RESULT]** [flavor]\n"
                "Or: 'No contested actions this round.'"
            ),
            min_words=5,  # "No contested actions this round" is a valid short response
        )

        print(f"\n--- Rules Keeper ---\n{rulings}\n")
        transcript.append(f"### Rules Keeper\n\n{rulings}")

        # --- Group D: Detect if initiative/combat was triggered this round ---
        initiative_triggered = (
            "INITIATIVE TRIGGERED" in rulings.upper() or
            "INITIATIVE ORDER" in rulings.upper() or
            "COMBAT HAS BEGUN" in rulings.upper()
        )
        # Also detect combat from PC attacks (Garrick charging, etc.)
        pc_attacked = any(
            keyword in combined_pc_actions.upper()
            for keyword in ["I ATTACK", "I SWING", "I CHARGE", "I STRIKE",
                           "ROLLS TO HIT", "ATTACK ROLL", "1D20+"]
        )
        if initiative_triggered or (pc_attacked and enemy_agents):
            combat_active = True

        # --- ENEMY ACTS AFTER PCs (PC-initiated combat) ---
        if enemy_agents and not enemy_goes_first and combat_active and not enemy_actions:
            enemy_actions, enemy_rulings = _run_enemy_turn(
                enemy_agents, rules_keeper, dm_narration,
                combined_pc_actions, combat_active, transcript
            )
            # Track whether enemy has actually attacked (vs just "no valid targets")
            if enemy_actions:
                if _has_real_attack(enemy_actions):
                    enemy_has_attacked = True
                    no_attack_exchanges = 0
                else:
                    no_attack_exchanges += 1
                    if enemy_has_attacked and no_attack_exchanges >= 2:
                        combat_active = False
                        print(f"[Session] Combat ended — no actual attacks for {no_attack_exchanges} "
                              f"consecutive exchanges (PC-initiated path, exchange {exchange_num})")
                    elif not enemy_has_attacked and no_attack_exchanges >= 3:
                        combat_active = False
                        combat_exchanges = 0
                        no_attack_exchanges = 0
                        print(f"[Session] Combat deactivated — enemy never attacked after "
                              f"{no_attack_exchanges} exchanges (false trigger, exchange {exchange_num})")
            # Detect combat ending from enemy actions or rulings
            if _check_combat_ended(enemy_actions, enemy_rulings):
                combat_active = False
                print(f"[Session] Combat ended — enemy defeated (PC-initiated path, exchange {exchange_num})")

        # --- DM responds to player actions + enemy actions + all rulings ---

        # Check if this is the final exchange
        is_final = (exchange_num == max_exchanges)

        # Check for human DM input
        mid_dm_input = ""
        if DM_INPUT_FILE.exists():
            raw = DM_INPUT_FILE.read_text(encoding="utf-8").strip()
            if raw:
                DM_INPUT_FILE.write_text("", encoding="utf-8")
                mid_dm_input = raw

        mid_dm_input_section = (
            f"\n\nSPECIAL INSTRUCTIONS FROM THE HUMAN DM (weave into your narration):\n"
            f"{mid_dm_input}"
            if mid_dm_input else ""
        )

        # Build the enemy context section for the DM
        enemy_context_section = ""
        if enemy_actions:
            enemy_context_section = (
                "\n\nENEMY ACTIONS THIS ROUND (declared by enemy agents — "
                "you MUST narrate these actions as happening, do NOT skip or soften them):\n\n"
                f"---\n{enemy_actions}\n---\n\n"
                "RULES KEEPER ADJUDICATION OF ENEMY ACTIONS:\n\n"
                f"---\n{enemy_rulings}\n---\n\n"
                "IMPORTANT: The enemy agent has declared these attacks independently. "
                "You narrate the RESULTS — describe the impacts, the damage, the chaos. "
                "Do NOT override the enemy's actions. Do NOT have the enemy pause, "
                "observe, speak, or negotiate instead of attacking. The attacks happened. "
                "Narrate them.\n"
            )

        combat_forcing_section = ""
        if combat_active and not enemy_actions:
            # Fallback for when combat is active but no enemy agent output
            # (e.g., enemy agents not configured for this adventure but initiative triggered)
            combat_forcing_section = (
                "\n\nCOMBAT IS ACTIVE — The Rules Keeper has rolled initiative. "
                "You MUST narrate combat this round. Describe the boss creature's "
                "attack actions using its stat block from the adventure file. "
                "Do NOT skip the creature's turn. Do NOT have the creature observe, "
                "study, pause, or communicate. It attacks on its initiative turn "
                "as prescribed in the adventure file.\n"
            )

        dm_continue_description = (
            f"REMINDER: You are running Adventure Session {adventure_session} of "
            f"{max_adventure_sessions}. Stay within the 'Session {adventure_session}' "
            f"section of the adventure file. Do NOT advance past the "
            f"'Session {adventure_session} Ends When' marker.\n\n"
            "The player characters have responded to your narration:\n\n"
            f"---\n{combined_pc_actions}\n---\n\n"
            "The Rules Keeper has adjudicated PC actions:\n\n"
            f"---\n{rulings}\n---\n\n"
            f"{enemy_context_section}"
            f"{combat_forcing_section}"
            f"{mid_dm_input_section}"
        )

        if is_final:
            dm_continue_description += (
                "This is the FINAL exchange of the session. Narrate the resolution "
                "of the current scene and bring the session to a natural dramatic "
                "pause — a cliffhanger, a moment of rest, or a significant milestone. "
                "Make it clear this is a stopping point that can be picked up next session."
            )
        else:
            dm_continue_description += (
                "Continue the story based on their actions. Narrate the consequences "
                "of what they did. Describe NPC reactions, environmental changes, "
                "and any new developments. If their actions trigger ability checks, "
                "set appropriate DCs and request rolls.\n\n"
                "End with a new situation that requires the players to respond."
            )

        dm_narration = run_single_agent_task(
            agent=dm,
            description=dm_continue_description,
            expected_output=(
                "A vivid narration (2-4 paragraphs) that advances the story based "
                "on player actions, with a clear prompt for what happens next."
            ),
        )

        print(f"\n--- DM ---\n{dm_narration}\n")
        transcript.append(f"## DM (Scene {exchange_num})\n\n{dm_narration}")

        # --- Hotfix: Detect combat ending from DM narration ---
        # Catches cases where the DM narrates the enemy dying but the enemy agent
        # and Rules Keeper didn't use recognized combat-end phrases.
        if combat_active and _check_combat_ended(dm_narration):
            combat_active = False
            print(f"[Session] Combat ended — enemy defeated (DM narration, exchange {exchange_num})")

        # --- Check if the DM declared the session over ---
        # If the DM writes a "session ends" marker, stop the loop immediately
        # instead of letting PCs respond and the DM generate more content.
        import re as _loop_re
        session_end_pattern = _loop_re.compile(
            r'SESSION\s+\d*\s*ENDS?\s+HERE|'
            r'SESSION\s+\d*\s*ENDS?\s+WHEN|'
            r'END\s+OF\s+SESSION|'
            r'SESSION\s+\d*\s*COMPLETE',
            _loop_re.IGNORECASE
        )
        if session_end_pattern.search(dm_narration) and not is_final:
            print(f"\n[Session] DM declared session end at exchange {exchange_num}/{max_exchanges}. "
                  f"Breaking loop early.")
            break

    # --- SESSION WRAP-UP ---
    print(f"\n{'='*60}")
    print(f"  SESSION {session_num} WRAP-UP")
    print(f"  API calls this session: {_api_call_count}")
    print(f"{'='*60}\n")

    full_transcript = "\n\n---\n\n".join(transcript)

    # --- Update campaign state ---
    print("[System] Updating campaign state...")
    state_description = (
        "Based on the following session transcript, update the campaign state. "
        "Use the 'Save Campaign State' tool with updated JSON that includes:\n"
        "- session_number (integer: keep the same value from current state — "
        "Python manages this field, do NOT change it)\n"
        "- current_location (where the party is now)\n"
        "- party (update HP if any damage/healing occurred, update inventory)\n"
        "- story_summary (STRICT MAX 300 WORDS. Summarize the ENTIRE campaign "
        "so far — not just this session — in a single concise paragraph. Focus on: "
        "key plot points, major decisions, and current objectives. Drop minor details, "
        "NPC dialogue, travel descriptions, and combat play-by-play. If the existing "
        "summary is already near 300 words, CONDENSE it — do not just append.)\n"
        "- active_quests (list of ACTIVE quest objectives ONLY. REMOVE any quest "
        "that was completed or failed this session. REMOVE vague duplicates — if two "
        "entries describe the same objective, keep only the more specific one. Each "
        "entry should be a concrete, actionable objective like 'Bounty on Emberfell "
        "Rejects: 50gp from Reyna Steelforge'. MAX 5 active quests.)\n"
        "- discovered_locations (list of places visited)\n"
        "- known_npcs (list of NPCs met)\n"
        "- current_adventure (integer: keep the same value from current state)\n"
        "- current_adventure_name (string: keep the same value from current state)\n"
        "- sessions_in_adventure (integer: keep the same value from current state — "
        "Python manages this field, do NOT change it)\n"
        "- max_sessions_per_adventure (integer: keep the same value from current state)\n"
        "- current_act (integer: which act of the campaign arc we are in)\n"
        "- next_beat (string: the next narrative milestone the story should reach — "
        "update this when the current beat was achieved this session, otherwise keep it)\n"
        "- sessions_in_current_beat (integer: how many sessions have passed working "
        "toward next_beat — reset to 0 when next_beat changes, otherwise increment by 1)\n\n"
        f"Current state:\n{json.dumps(state, indent=2)}\n\n"
        f"Session transcript:\n{full_transcript}"
    )

    run_single_agent_task(
        agent=dm,
        description=state_description,
        expected_output="Confirmation that the campaign state has been saved.",
    )

    # Reload the state that the DM saved
    state = load_state()

    # --- Wiki Keeper extracts entities as JSON, Python writes the files ---
    # Why JSON instead of tool calls: DeepSeek reliably generates JSON text but
    # stalls on multi-step tool call sequences. We have Python write the files.
    # NOTE: Wiki runs BEFORE the Scribe so we can inject exact entity names into
    # the Scribe's task, guaranteeing [[wiki links]] match real files on disk.
    print("[Wiki Keeper] Extracting entities...")
    wiki_description = (
        f"You are extracting SIGNIFICANT named entities from a D&D session "
        f"transcript (Session {session_num}) for a campaign wiki.\n\n"
        "Session transcript:\n\n"
        f"---\n{full_transcript}\n---\n\n"
        "Output a JSON array of ONLY significant proper nouns that deserve "
        "their own wiki page. Quality over quantity.\n\n"
        "INCLUDE: Named NPCs (Reyna Steelforge), named locations (Grimhold, "
        "Second Wind Inn), named factions (Emberfell Rejects), unique named "
        "items (Kregg's +1 Dagger), named lore concepts (The First World Sleeper).\n\n"
        "EXCLUDE: The three PCs (Cora Flint, Garrick Kade, Professor Mercer), "
        "generic objects (rope, crossbow, rations), unnamed locations (the courtyard, "
        "the trail), action-events (the ambush, the negotiation), spells and game "
        "mechanics, common nouns.\n\n"
        "Each element must have these fields:\n"
        '  "name":        exact proper noun (e.g. "Reyna Steelforge", "Second Wind Inn")\n'
        '  "type":        one of: npc | location | item | faction | lore\n'
        '  "status":      one of: alive | dead | unknown | exists | destroyed\n'
        '  "location":    where this entity is found (empty string if not applicable)\n'
        '  "description": one sentence summary of what this entity is\n'
        '  "history":     1 sentence about what happened with this entity '
        "in this session. Use [[Name]] brackets around any proper nouns you mention.\n\n"
        "Output ONLY the raw JSON array. No explanation, no markdown fences, "
        "no other text. Start your response with [ and end with ]."
    )

    wiki_json = run_single_agent_task(
        agent=wiki_keeper,
        description=wiki_description,
        expected_output=(
            "A raw JSON array of 5-15 entity objects for significant proper nouns "
            "found in the session transcript. Quality over quantity."
        ),
    )

    wiki_count, new_wiki_names = write_wiki_from_json(wiki_json, session_num)
    print(f"\n[Wiki] {wiki_count} file(s) written to output/wiki/\n")

    # Collect the exact entity names now on disk so the Scribe can link to them
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    wiki_entity_names = sorted(
        p.stem for p in WIKI_DIR.glob("*.md")
    )
    if wiki_entity_names:
        wiki_link_list = ", ".join(f"[[{n}]]" for n in wiki_entity_names)
        wiki_link_section = (
            f"\n\nKNOWN WIKI ENTITIES — use ONLY these exact names inside [[ ]] brackets:\n"
            f"{wiki_link_list}\n"
            "Do not invent link names that are not in this list."
        )
    else:
        wiki_link_section = ""

    # --- Scribe writes the session blog ---
    # Python writes the file directly — same reason as DM opening and Wiki Keeper:
    # DeepSeek sometimes garbles the JSON tool arguments for long string content,
    # causing "Unterminated string" errors. The Scribe just outputs the narrative
    # text; Python handles saving it.
    print("[Scribe] Writing session narrative...")
    scribe_description = (
        f"Write the narrative blog post for Session {session_num}. "
        "Transform the following raw session transcript into a compelling "
        "in-world narrative journal entry. Write as a historian or chronicler "
        "who witnessed these events.\n\n"
        f"Session Transcript:\n{full_transcript}"
        f"{wiki_link_section}\n\n"
        "YOUR OUTPUT: Write the full narrative directly. Do NOT call any tools. "
        "Just output the polished markdown narrative text and nothing else. "
        f"Start with a header like '# Session {session_num}: [Title]'."
    )

    blog_content = run_single_agent_task(
        agent=scribe,
        description=scribe_description,
        expected_output=(
            "A polished markdown narrative of 800-1500 words capturing the "
            "session's events in an engaging, in-world storytelling style."
        ),
    )

    # Write the blog file directly in Python
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    blog_path = SESSIONS_DIR / f"session_{session_num:02d}.md"
    blog_path.write_text(blog_content, encoding="utf-8")
    print(f"[Scribe] Blog saved to {blog_path}\n")

    # --- Editor: post-session fact-check ---
    # Runs after both Scribe and Wiki Keeper. Checks session report and new wiki
    # entries against the gameplay transcript AND adventure file. Returns invention
    # flags so the Lorekeeper can exclude invented content from wiki entries.
    editor_invention_flags = run_editor_session(
        full_transcript=full_transcript,
        session_num=session_num,
        blog_path=blog_path,
        new_wiki_names=new_wiki_names,
        story_summary=state.get("story_summary", ""),
        adventure_text=dm_ctx.get("adventure", ""),
        use_claude=creative_use_claude,
    )

    # --- Lorekeeper: per-session consistency pass ---
    # Receives Editor's invention flags to prevent codifying invented content
    state = run_lorekeeper_session(
        state=state,
        session_num=session_num,
        blog_path=blog_path,
        new_wiki_names=new_wiki_names,
        adventure_text=dm_ctx.get("adventure", ""),
        use_claude=creative_use_claude,
        editor_invention_flags=editor_invention_flags,
    )

    # --- Check for adventure completion and swap ---
    # Reload state fresh (DM may have saved new values) and ensure Python-managed
    # fields are correct before checking adventure progress.
    state = load_state()
    state["session_number"] = session_num  # Python is authoritative
    # Only restore sessions_in_adventure if the adventure hasn't already advanced.
    # Guard against double-advance: if advance_adventure() already ran (e.g. due to
    # CrewAI concurrency), current_adventure will have incremented and
    # sessions_in_adventure will be 0. Don't overwrite it back to 3.
    if state.get("current_adventure") == adventure_num:
        state["sessions_in_adventure"] = adventure_session  # Python is authoritative
    save_state(state)

    adventure_completed = advance_adventure(state, party_levels=party_levels)

    # Condense story summary and clean quest list at adventure boundaries
    if adventure_completed:
        state = load_state()  # Reload after advance_adventure saved

        # Generate adventure summary from the 3 session reports
        print(f"[Summary] Generating adventure {adventure_num} summary...")
        session_reports = []
        for s in range(session_num - 2, session_num + 1):
            report_path = SESSIONS_DIR / f"session_{s:02d}.md"
            if report_path.exists():
                session_reports.append(report_path.read_text(encoding="utf-8"))
        if session_reports:
            combined_reports = "\n\n---\n\n".join(session_reports)
            adv_summary_text = run_single_agent_task(
                agent=dm,
                description=(
                    f"Write a 1-2 sentence summary of Adventure {adventure_num}: "
                    f"{adventure_name}. Base it ONLY on what actually happened in "
                    f"these session reports:\n\n{combined_reports}\n\n"
                    "Write in past tense. Focus on what the party did and what "
                    "the outcome was. Do NOT include spoilers for future adventures. "
                    "Output ONLY the summary text, nothing else."
                ),
                expected_output="A 1-2 sentence adventure summary.",
            )
            # Store in campaign state
            adventure_summaries = state.get("adventure_summaries", {})
            adventure_summaries[str(adventure_num)] = adv_summary_text.strip()
            state["adventure_summaries"] = adventure_summaries
            print(f"[Summary] Adventure {adventure_num} summary saved.")

        # Condense story summary
        condensed = condense_story_summary(state, dm_agent=dm)
        state["story_summary"] = condensed

        # Clean quest list — remove completed/stale quests from finished adventure
        quests = state.get("active_quests", [])
        if quests:
            print(f"[Quests] Cleaning quest list ({len(quests)} entries)...")
            cleaned_json = run_single_agent_task(
                agent=dm,
                description=(
                    "You are cleaning up the active quest list after an adventure "
                    f"completed. Adventure {adventure_num} ({adventure_name}) is DONE.\n\n"
                    f"Current active_quests:\n{json.dumps(quests, indent=2)}\n\n"
                    f"Story so far:\n{state.get('story_summary', '')}\n\n"
                    "Return a JSON array of ONLY quests that are still unresolved and "
                    "relevant going forward. REMOVE any quest that:\n"
                    "- Was completed or resolved during the adventure that just ended\n"
                    "- Is vague or duplicated by another entry\n"
                    "- References events that are no longer relevant\n\n"
                    "If ALL quests are resolved, return an empty array: []\n"
                    "Output ONLY the raw JSON array. No explanation."
                ),
                expected_output="A JSON array of remaining active quest strings.",
                min_words=3,  # Quest JSON arrays can be very short
            )
            # Parse the cleaned quest list
            import re
            cleaned_text = cleaned_json.strip()
            fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned_text)
            if fence_match:
                cleaned_text = fence_match.group(1)
            else:
                arr_match = re.search(r'\[[\s\S]*\]', cleaned_text)
                if arr_match:
                    cleaned_text = arr_match.group()
            try:
                cleaned_quests = json.loads(cleaned_text)
                if isinstance(cleaned_quests, list):
                    state["active_quests"] = cleaned_quests
                    print(f"[Quests] Cleaned: {len(quests)} → {len(cleaned_quests)} quests.")
            except json.JSONDecodeError:
                print("[Quests] Warning: could not parse cleaned quests. Keeping original.")

        # --- Legendary Boons: award after final adventure (Adventure 20) ---
        if adventure_num == 20:
            print("[Boons] Campaign finale complete — awarding Legendary Boons...")
            boons = {
                "Cora Flint": "Boon of the Maker: Advantage on all crafting and repair checks. "
                              "Once per day, can instantly repair any non-magical object.",
                "Garrick Kade": "Boon of the Guardian: +2 AC when within 10 ft of an ally. "
                                "Once per day, can take a hit meant for an adjacent ally.",
                "Professor Thaddeus Mercer": "Boon of the Scholar: Advantage on all Arcana, "
                                             "History, and Investigation checks. Once per day, "
                                             "can ask one yes/no question about any topic and "
                                             "receive a truthful answer.",
            }
            for char_name, boon in boons.items():
                if char_name in state.get("party", {}):
                    party_member = state["party"][char_name]
                    conditions = party_member.get("conditions", "")
                    party_member["conditions"] = f"{conditions}; {boon}" if conditions else boon
                    print(f"  [Boon] {char_name}: {boon.split(':')[0]}")

        save_state(state)

        # --- Lorekeeper: end-of-adventure full wiki editorial pass ---
        run_lorekeeper_adventure(state=state, use_claude=creative_use_claude)

    # Generate clean transcript from the raw session log
    try:
        from transcript import process_log
        log_path = LOGS_DIR / f"session_{session_num:02d}_log.txt"
        if log_path.exists():
            process_log(log_path)
    except Exception as e:
        print(f"[Transcript] Warning: could not generate transcript ({e})")

    print(f"\n{'='*60}")
    print(f"  SESSION {session_num} COMPLETE")
    print(f"  Blog saved to: output/sessions/session_{session_num:02d}.md")
    print(f"  Transcript saved to: output/sessions/session_{session_num:02d}_transcript.md")
    print(f"  Log saved to: output/logs/session_{session_num:02d}_log.txt")
    print(f"  Reviews saved to: output/reviews/")
    print(f"  Wiki updated in: output/wiki/")
    print(f"  State saved to: campaign_state.json")
    if adventure_completed:
        print(f"  >>> Adventure {adventure_num} complete! Next adventure loaded.")
        print(f"  >>> Story summary condensed for next adventure.")
    print(f"{'='*60}\n")
