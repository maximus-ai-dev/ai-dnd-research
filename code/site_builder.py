"""
site_builder.py — Generates the static site for laternia.maxcapa.city

Reads from:
  output/sessions/     session reports + transcripts (markdown)
  output/wiki/         wiki entries (markdown)
  campaign_state.json  current party/quest/adventure state
  campaign_arc.md      full 20-adventure campaign structure
  CHANGELOG.md         version history (auto-appended, hand-editable)

Writes to:
  docs/                complete static site, served by Vercel from GitHub

Called automatically at the end of each session run, or standalone:
  python site_builder.py
"""

import json
import random
import re
import shutil
from datetime import datetime
from pathlib import Path

import markdown as md_lib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
SESSIONS_DIR = OUTPUT_DIR / "sessions"
WIKI_DIR = OUTPUT_DIR / "wiki"
DOCS_DIR = BASE_DIR / "docs"
CAMPAIGN_STATE_FILE = BASE_DIR / "campaign_state.json"
CAMPAIGN_ARC_FILE = BASE_DIR / "campaign_arc.md"
CHANGELOG_FILE = BASE_DIR / "CHANGELOG.md"

# ---------------------------------------------------------------------------
# Site config — update CURRENT_RUN when starting a new campaign
# ---------------------------------------------------------------------------
SITE_TITLE = "Laternia"
SITE_SUBTITLE = 'An Autonomous AI D&amp;D Campaign World by <a href="https://maxcapa.city">Max Capacity</a>'
CAMPAIGN_NAME = "The Asymmetrical Mountain"
TOTAL_ADVENTURES = 20
SESSIONS_PER_ADVENTURE = 1
TOTAL_SESSIONS = TOTAL_ADVENTURES * SESSIONS_PER_ADVENTURE  # 20

_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br"]

# ---------------------------------------------------------------------------
# ASCII art pool — one is chosen at random each site build
# ---------------------------------------------------------------------------
ASCII_ART_POOL = [
    # Castle on the Asymmetrical Mountain (character art)
    (
        '                                                                                \n'
        '                                  -+                .:=                         \n'
        '                                  .@+              := ==                        \n'
        '                   -            :  @@+           =:  #*@%                       \n'
        '                   *@          =*-.@@@*          =-  *@@#           %-          \n'
        '                   %@%        =+ ==-*@@+          =  +@@*         . @@+         \n'
        '                 :+@@@@        :.   =##    +*--:-:++=*@@* +     .- *@@@@        \n'
        '                +%  :@@@.       +: #@@%:+=.=-  .  :+##++#%@-   -=  #@#@@@=      \n'
        '              . == .+@@@@-      +: =#=::==. .        +@%@@     =*: .::*=#-      \n'
        '             .:.:=*#%@@@@@%=    +=.        -. -      *@%-@       = .:*@#        \n'
        '           .-      ..-=++#@*    ++-           %@  =  *@@#%#*%=*%.##+.@@@        \n'
        '            -      +%@@@@@@+  #:  +  :      - .@# =  *@@@-*@@@@+@@@- @@@ =*     \n'
        '             :      :-==+#  :+#.  + .  -    -  @#    =@@@#.%@@@.@@@..@@# #@-    \n'
        '      -+     :     *@@@@@@  *@*:-+= ..-=:.  - +@@% %% :-@*  #@@*%@@@@==  @@@  #@\n'
        '     = =:    -     *@@@@@@. =: . ..  .  @@%#%#%%%@.@@%%%    %@    +@#    @@%*.@@\n'
        '     *       .     +@@@@@@     .   .   .@@@@*#    :@@% : :@ %@    :@* :. %@@@:=@\n'
        '     =             =%@@@@-         :   .@@%-@@ -  -@@%   :@*@%*=.        %@@%-+*\n'
        '                   .#@@@.               @@@@@.    -@@@    @@=:-*=:..     +@@@@@@\n'
        '              +@@@@@%#.                 #@@@@      .=+.  :@@@@@@@@@@@@*   :@@@@@\n'
        '            -%@%*=:                  #@@@@@@@@#-          %@%@@@@@@@@@@@%=  .*@%'
    ),
]

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,600;1,400&display=swap');

:root {
  --bg:          #0a0a0a;
  --text:        #d4d4d4;
  --heading:     #ffffff;
  --link:        #4dff91;
  --wiki-link:   #c084fc;
  --dim:         #808080;
  --border:      #1e1e1e;
  --surface:     #0f0f0f;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html { font-size: 16px; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'IBM Plex Mono', 'Courier New', monospace;
  line-height: 1.75;
  max-width: 80ch;
  margin: 0 auto;
  padding: 2.5rem 1.5rem 4rem;
}

/* --- Typography --- */
h1, h2, h3, h4 {
  color: var(--heading);
  line-height: 1.25;
  margin: 2rem 0 0.6rem;
}
h1 { font-size: 1.5rem; letter-spacing: 0.02em; }
h2 { font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }
h3 { font-size: 1rem; }
h4 { font-size: 0.9rem; color: var(--link); text-transform: uppercase; letter-spacing: 0.05em; }

p  { margin: 0.8rem 0; }
em { font-style: italic; }
strong { font-weight: 600; color: var(--heading); }

ul, ol { margin: 0.8rem 0 0.8rem 1.5rem; }
li { margin: 0.25rem 0; }

blockquote {
  border-left: 2px solid var(--border);
  margin: 1.2rem 0;
  padding: 0.5rem 1.2rem;
  color: var(--dim);
  font-style: italic;
}

hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2.5rem 0;
}

code {
  background: var(--surface);
  padding: 0.15rem 0.35rem;
  font-size: 0.88em;
  font-family: inherit;
}

pre {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 1.2rem;
  overflow-x: auto;
  margin: 1.2rem 0;
  font-size: 0.88em;
}
pre code { background: none; padding: 0; }

/* --- Links --- */
a               { color: var(--link); text-decoration: none; }
a:hover         { text-decoration: underline; }
a.wiki-link     { color: var(--wiki-link); }
a.wiki-link:hover { text-decoration: underline; }
.wiki-link-dead { color: var(--wiki-link); opacity: 0.45; cursor: default; }

/* --- Navigation --- */
nav {
  margin-bottom: 3rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0;
}
.nav-title {
  color: var(--heading);
  font-weight: 600;
  margin-right: 2rem;
  font-size: 0.95rem;
}
nav a { margin-right: 1.75rem; }
nav a.active { color: var(--heading); text-decoration: underline; }

/* --- Breadcrumb --- */
.breadcrumb {
  color: var(--dim);
  font-size: 0.82rem;
  margin-bottom: 1.75rem;
}
.breadcrumb a { color: var(--dim); }
.breadcrumb a:hover { color: var(--link); }
.breadcrumb span { color: var(--text); }

/* --- Progress --- */
.progress-section { margin: 2rem 0; }
.progress-row {
  display: grid;
  grid-template-columns: 3ch 1fr auto;
  gap: 0 1.5rem;
  align-items: baseline;
  margin: 0.3rem 0;
  font-size: 0.88rem;
}
.progress-bar-fill  { color: var(--link); }
.progress-bar-empty { color: var(--border); }
.progress-count { color: var(--dim); white-space: nowrap; }
.progress-status-done     { color: var(--dim); }
.progress-status-active   { color: var(--link); }
.progress-status-locked   { color: var(--border); }
.progress-adv-name { color: var(--text); }
.progress-adv-name.done   { color: var(--dim); }
.progress-adv-name.locked { color: var(--border); }
.progress-act-header {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--dim);
  margin: 1rem 0 0.3rem;
}

/* --- Session list --- */
.session-list { list-style: none; margin: 1rem 0; }
.session-list li {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: baseline;
  gap: 1rem;
  flex-wrap: wrap;
}
.session-num    { color: var(--dim); font-size: 0.82rem; flex-shrink: 0; min-width: 6ch; }
.session-title  { flex: 1; }
.transcript-tag {
  font-size: 0.78rem;
  color: var(--dim);
  flex-shrink: 0;
}
.transcript-tag a { color: var(--dim); }
.transcript-tag a:hover { color: var(--link); }

/* --- Wiki index --- */
.wiki-index {
  columns: 2;
  column-gap: 3rem;
  margin: 1rem 0;
}
@media (max-width: 55ch) { .wiki-index { columns: 1; } }
.wiki-index a {
  display: block;
  padding: 0.2rem 0;
  color: var(--wiki-link);
}

/* --- State block (quests, party) --- */
.state-block {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 1rem 1.5rem;
  margin: 1.5rem 0;
  font-size: 0.88rem;
}
.state-block h4 { margin-top: 0; margin-bottom: 0.6rem; }
.state-block ul { list-style: none; padding: 0; margin: 0; }
.state-block li { padding: 0.15rem 0; }
.state-block li::before { content: '> '; color: var(--dim); }

/* --- Session nav bar --- */
.session-nav {
  display: flex;
  border: 1px solid var(--border);
  font-size: 0.8rem;
  margin: 1.75rem 0;
  overflow: hidden;
}
.session-nav a, .session-nav span {
  flex: 1;
  padding: 0.5rem 0.75rem;
  text-align: center;
  border-right: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-nav a:last-child, .session-nav span:last-child { border-right: none; }
.session-nav a { color: var(--link); }
.session-nav a:hover { background: var(--surface); text-decoration: none; }
.session-nav .nav-center { color: var(--dim); }
.session-nav .nav-dead { color: var(--border); cursor: default; }

/* --- Latest session card --- */
.latest-session {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 1rem 1.5rem;
  margin: 1.5rem 0;
}
.latest-session h4 { margin-top: 0; margin-bottom: 0.6rem; }
.latest-title { font-size: 1.05rem; }
.latest-teaser {
  color: var(--text);
  font-style: italic;
  font-size: 0.88rem;
  margin: 0.6rem 0;
  line-height: 1.6;
}

/* --- Notice banners --- */
.notice {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 0.6rem 1rem;
  margin-bottom: 1.75rem;
  font-size: 0.82rem;
  color: var(--dim);
}
.notice a { color: var(--dim); }
.notice a:hover { color: var(--link); }

/* --- Transcript --- */
.transcript-body strong { color: var(--link); }
.transcript-body blockquote { font-style: normal; font-size: 0.88em; }

/* --- Footer --- */
footer {
  margin-top: 4rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  color: var(--dim);
  font-size: 0.78rem;
}
footer a { color: var(--dim); }
footer a:hover { color: var(--link); }

/* --- ASCII Art --- */
.ascii-art {
  font-size: 0.98rem;
  line-height: 1.1;
  color: var(--text);
  margin: 1.5rem 0;
  overflow: hidden;
  white-space: pre;
  background: none;
  border: none;
  padding: 0;
}

/* --- Adventure list --- */
.adv-row {
  padding: 0.2rem 0;
}

/* --- Utility --- */
.dimmed  { color: var(--dim); }
.section-title {
  color: var(--dim);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin: 2rem 0 0.75rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3rem;
}
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert a display name to a URL-safe slug."""
    s = name.lower()
    s = re.sub(r"['\"+#@!?.,;:()\\]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def md_to_html(text: str) -> str:
    """Convert markdown to HTML."""
    return md_lib.markdown(text, extensions=_MD_EXTENSIONS)


def resolve_wiki_links(html: str, wiki_slugs: set[str]) -> str:
    """Replace [[Name]] patterns with anchor tags.
    Must be called on raw markdown BEFORE md_to_html, since markdown
    will escape brackets inside already-rendered HTML.
    """
    def replace(m):
        name = m.group(1).strip()
        slug = slugify(name)
        if slug in wiki_slugs:
            return f'<a href="/wiki/{slug}/" class="wiki-link">{name}</a>'
        return f'<span class="wiki-link-dead" title="Wiki entry not yet written">{name}</span>'

    return re.sub(r'\[\[([^\]]+)\]\]', replace, html)


def render_page(
    title: str,
    content: str,
    breadcrumb: str = "",
    active_nav: str = "",
    extra_class: str = "",
) -> str:
    """Wrap content in the full HTML shell."""
    nav_links = [
        ("home",      "/",              "Home"),
        ("campaigns", "/campaigns/",    "Campaigns"),
        ("wiki",      "/wiki/",         "Wiki"),
        ("readme",    "/readme/",       "Readme"),
        ("changelog", "/changelog/",    "Changelog"),
    ]
    nav_html = f'<span class="nav-title">{SITE_TITLE}</span>'
    for key, href, label in nav_links:
        cls = ' class="active"' if key == active_nav else ""
        nav_html += f'<a href="{href}"{cls}>{label}</a>'

    breadcrumb_html = f'<div class="breadcrumb">{breadcrumb}</div>' if breadcrumb else ""
    body_class = f' class="{extra_class}"' if extra_class else ""

    built = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title if title == SITE_TITLE else f"{title} — {SITE_TITLE}"}</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body{body_class}>
  <nav>{nav_html}</nav>
  {breadcrumb_html}
  <main>
{content}
  </main>
  <footer>
    {SITE_TITLE} &mdash; {SITE_SUBTITLE} &mdash;
    <a href="https://laternia.maxcapa.city">laternia.maxcapa.city</a>
    &mdash; built {built}
  </footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Campaign arc parser
# ---------------------------------------------------------------------------

def parse_campaign_arc() -> list[dict]:
    """Parse campaign_arc.md into a list of adventure dicts.

    Returns:
        [{"num": 1, "name": "The Desperate Bounty", "level": 1, "act": "I"}, ...]
    """
    if not CAMPAIGN_ARC_FILE.exists():
        return []

    text = CAMPAIGN_ARC_FILE.read_text(encoding="utf-8")
    adventures = []
    current_act = ""

    act_re = re.compile(r"^## Act ([IVX]+):", re.MULTILINE)
    adv_re = re.compile(
        r"^\d+\.\s+\*\*Adventure\s+(\d+)\s+[—–-]+\s+(.+?)\s+\(Level\s+(\d+)",
        re.MULTILINE,
    )

    # Build a map: line_pos → act_label
    act_positions = [(m.start(), m.group(1)) for m in act_re.finditer(text)]

    for m in adv_re.finditer(text):
        pos = m.start()
        act = ""
        for apos, alabel in act_positions:
            if apos <= pos:
                act = alabel
        adventures.append({
            "num":   int(m.group(1)),
            "name":  m.group(2).strip(),
            "level": int(m.group(3)),
            "act":   act,
        })

    return adventures


# ---------------------------------------------------------------------------
# Progress bar renderer
# ---------------------------------------------------------------------------

def render_overall_bar(sessions_done: int) -> str:
    """Render the overall [###...] N / 20 sessions bar."""
    filled = min(sessions_done, TOTAL_SESSIONS)
    bar_width = 30
    n_fill = round((filled / TOTAL_SESSIONS) * bar_width)
    bar = (
        '<span class="progress-bar-fill">' + "#" * n_fill + "</span>"
        + '<span class="progress-bar-empty">' + "." * (bar_width - n_fill) + "</span>"
    )
    return (
        f'<p>[{bar}] '
        f'{sessions_done} / {TOTAL_SESSIONS} sessions</p>'
    )


def render_progress(state: dict, adventures: list[dict], sessions_done: int,
                    include_overall: bool = True) -> str:
    """Render the ASCII-style campaign progress section."""
    current_adv = state.get("current_adventure", 1)
    sessions_in_adv = state.get("sessions_in_adventure", 0)

    lines = [
        f'<div class="section-title">Campaign Progress</div>',
        f'<div class="progress-section">',
    ]

    if include_overall:
        lines.append(render_overall_bar(sessions_done))
        lines.append("<br>")

    # Per-adventure rows (show all 20, locked ones greyed out)
    # Group by act — insert a header row when the act changes
    current_act_label = ""
    for adv in adventures:
        num = adv["num"]
        name = adv["name"]
        act = adv.get("act", "")
        if act and act != current_act_label:
            current_act_label = act
            lines.append(
                f'<div class="progress-act-header">Act {act}</div>'
            )

        if num < current_adv:
            # Completed
            adv_bar = '<span class="progress-bar-fill">' + "##" * SESSIONS_PER_ADVENTURE + "</span>"
            status = '<span class="progress-status-done">done</span>'
            name_cls = "done"
            display_name = name
        elif num == current_adv:
            # In progress
            n = min(sessions_in_adv, SESSIONS_PER_ADVENTURE)
            adv_bar = (
                '<span class="progress-bar-fill">' + "##" * n + "</span>"
                + '<span class="progress-bar-empty">' + ".." * (SESSIONS_PER_ADVENTURE - n) + "</span>"
            )
            status = '<span class="progress-status-active">active</span>'
            name_cls = ""
            display_name = name
        elif num == current_adv + 1:
            # Next adventure — show as a teaser
            adv_bar = '<span class="progress-bar-empty">' + ".." * SESSIONS_PER_ADVENTURE + "</span>"
            status = '<span class="progress-status-locked">---</span>'
            name_cls = "locked"
            display_name = name
        else:
            # Future — hidden
            adv_bar = '<span class="progress-bar-empty">' + ".." * SESSIONS_PER_ADVENTURE + "</span>"
            status = '<span class="progress-status-locked">---</span>'
            name_cls = "locked"
            display_name = "???"

        lines.append(
            f'<div class="progress-row">'
            f'<span class="dimmed">{num:02d}</span>'
            f'<span>[{adv_bar}] '
            f'<span class="progress-adv-name {name_cls}">{display_name}</span></span>'
            f'<span class="progress-count">{status}</span>'
            f'</div>'
        )

    lines.append("</div>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session nav bar helper
# ---------------------------------------------------------------------------

def session_nav(
    prev_num: int | None,
    next_num: int | None,
    campaign_url: str,
    prev_url_tmpl: str,
    next_url_tmpl: str,
) -> str:
    """Render the < PREVIOUS SESSION | RETURN TO CAMPAIGN | NEXT SESSION > bar."""
    if prev_num is not None:
        prev_slug = f"{prev_num:02d}"
        prev_cell = (
            f'<a href="{prev_url_tmpl.format(prev_slug)}">'
            f'&laquo; SESSION {prev_slug}</a>'
        )
    else:
        prev_cell = '<span class="nav-dead">&laquo; PREVIOUS</span>'

    center_cell = (
        f'<a class="nav-center" href="{campaign_url}">CAMPAIGN</a>'
    )

    if next_num is not None:
        next_slug = f"{next_num:02d}"
        next_cell = (
            f'<a href="{next_url_tmpl.format(next_slug)}">'
            f'SESSION {next_slug} &raquo;</a>'
        )
    else:
        next_cell = '<span class="nav-dead">NEXT &raquo;</span>'

    return f'<nav class="session-nav">{prev_cell}{center_cell}{next_cell}</nav>'


# ---------------------------------------------------------------------------
# Individual page builders
# ---------------------------------------------------------------------------

def build_homepage(state: dict, adventures: list[dict], sessions: list[dict], wiki_slugs: set[str] = None) -> str:
    """Build the homepage (index.html)."""
    sessions_done = len(sessions)
    current_adv_name = state.get("current_adventure_name", CAMPAIGN_NAME)
    current_location = state.get("current_location", "")
    party = state.get("party", {})
    story_summary = state.get("story_summary", "")
    active_quests = state.get("active_quests", [])

    # Party levels
    levels = []
    for name, info in party.items():
        cls = info.get("class", "")
        # Extract class with subclass (e.g. "Alchemist" from "Artificer (Alchemist) 5")
        sub_match = re.search(r'\(([^)]+)\)', cls) if cls else None
        base_class = cls.split("(")[0].strip().rstrip("0123456789 ") if cls else ""
        short_class = sub_match.group(1) if sub_match else base_class
        if short_class:
            levels.append(f"{name} — {short_class} (lvl {info.get('level', 1)})")
        else:
            levels.append(f"{name} (lvl {info.get('level', 1)})")

    # Latest session — card with teaser text
    latest_html = ""
    if sessions:
        latest = sessions[-1]
        prev   = sessions[-2] if len(sessions) >= 2 else None
        num_str = f"{latest['num']:02d}"

        # Extract opening line from session report as teaser
        teaser = ""
        raw_text = latest["raw"]
        # Skip the title line, find the first real paragraph
        for line in raw_text.split("\n"):
            stripped = line.strip().strip("*_")  # strip markdown emphasis markers
            if stripped and not stripped.startswith("#") and len(stripped) > 30:
                # Truncate to ~200 chars at a word boundary
                if len(stripped) > 200:
                    teaser = stripped[:200].rsplit(" ", 1)[0] + "..."
                else:
                    teaser = stripped
                break

        if teaser and wiki_slugs:
            teaser = resolve_wiki_links(teaser, wiki_slugs)
        teaser_html = f'<p class="latest-teaser">{teaser}</p>' if teaser else ""

        latest_html = (
            f'<div class="latest-session">'
            f'<h4>Latest Session</h4>'
            f'<p class="latest-title">'
            f'<a href="/campaigns/sessions/{num_str}/">'
            f'#{num_str} &mdash; {latest["title"]}</a>'
            f'&ensp;<span class="transcript-tag">'
            f'<a href="/campaigns/sessions/{num_str}/transcript/">[transcript]</a>'
            f'</span></p>'
            f'{teaser_html}'
            f'<p style="margin-top:0.75rem;">'
            f'<a href="/campaigns/">All {len(sessions)} sessions &rarr;</a>'
            f'</p>'
            f'</div>'
        )

    # Active quests
    quest_html = ""
    if active_quests:
        quest_items = "".join(f"<li>{q}</li>" for q in active_quests)
        quest_html = (
            '<div class="state-block">'
            '<h4>Active Quests</h4>'
            f'<ul>{quest_items}</ul>'
            '</div>'
        )

    # Party block
    party_html = ""
    if levels:
        party_items = "".join(f"<li>{l}</li>" for l in levels)
        party_html = (
            '<div class="state-block">'
            '<h4>The Party</h4>'
            f'<ul>{party_items}</ul>'
            f'<p style="margin-top:0.6rem;color:var(--dim);font-size:0.85em;">'
            f'Location: {current_location}</p>'
            '</div>'
        )

    story_html = ""
    if story_summary:
        story_html = f'<div class="section-title">Story So Far</div><p>{story_summary}</p>'

    overall_bar = render_overall_bar(sessions_done)

    # Build adventure list for homepage (no synopses, just names)
    current_adv = state.get("current_adventure", 1)
    if current_adv == TOTAL_ADVENTURES and sessions_done >= TOTAL_SESSIONS:
        current_adv = TOTAL_ADVENTURES + 1

    adv_lines = []
    current_act_label = ""
    for adv in adventures:
        num = adv["num"]
        name = adv["name"]
        act = adv.get("act", "")

        if act and act != current_act_label:
            current_act_label = act
            adv_lines.append(f'<div class="progress-act-header">Act {act}</div>')

        if num < current_adv:
            adv_lines.append(
                f'<div class="adv-row">'
                f'<a href="/campaigns/adventures/{num:02d}/">'
                f'{num:02d}. {name}</a>'
                f'</div>'
            )
        elif num == current_adv:
            adv_lines.append(
                f'<div class="adv-row">'
                f'<a href="/campaigns/adventures/{num:02d}/">'
                f'{num:02d}. {name}</a>'
                f' <span class="progress-status-active">active</span>'
                f'</div>'
            )
        elif num == current_adv + 1:
            adv_lines.append(
                f'<div class="adv-row dimmed">'
                f'{num:02d}. {name}'
                f'</div>'
            )
        else:
            adv_lines.append(
                f'<div class="adv-row dimmed">'
                f'{num:02d}. ???'
                f'</div>'
            )

    homepage_adv_list = "\n".join(adv_lines)

    ascii_castle = '<pre class="ascii-art">' + random.choice(ASCII_ART_POOL) + '</pre>'

    ascii_title = (
        '<pre class="ascii-art" style="font-size: 0.98rem; margin: 1rem 0 0.5rem;">'
        '░█░░░█▀█░▀█▀░█▀▀░█▀▄░█▀█░▀█▀░█▀█\n'
        '░█░░░█▀█░░█░░█▀▀░█▀▄░█░█░░█░░█▀█\n'
        '░▀▀▀░▀░▀░░▀░░▀▀▀░▀░▀░▀░▀░▀▀▀░▀░▀</pre>'
    )

    content = f"""{ascii_title}
<p class="dimmed">An Autonomous AI D&amp;D Campaign World by <a href="https://maxcapa.city">Max Capacity</a></p>
{ascii_castle}
<p>{CAMPAIGN_NAME} &mdash; {current_adv_name}</p>
{overall_bar}

<hr>

{story_html}
{party_html}

<hr>

{latest_html}

<hr>

{quest_html}

<div class="section-title">Adventures</div>
{homepage_adv_list}
"""
    return render_page(SITE_TITLE, content, active_nav="home")


def build_campaigns_page(state: dict, adventures: list[dict], sessions: list[dict]) -> str:
    """Build /campaigns/index.html — adventures grouped by act."""
    sessions_done = len(sessions)
    current_adv = state.get("current_adventure", 1)

    # If the campaign is complete (all 20 adventures done), current_adv may
    # still equal TOTAL_ADVENTURES. Detect this by checking if the final
    # session exists.
    if current_adv == TOTAL_ADVENTURES and sessions_done >= TOTAL_SESSIONS:
        current_adv = TOTAL_ADVENTURES + 1  # marks adventure 20 as complete

    # Adventure summaries from campaign_state.json (full narrative synopses)
    adventure_summaries = state.get("adventure_summaries", {})

    progress_html = render_progress(state, adventures, sessions_done)

    # Build adventure list grouped by act
    adv_lines = []
    current_act_label = ""
    for adv in adventures:
        num = adv["num"]
        name = adv["name"]
        act = adv.get("act", "")

        if act and act != current_act_label:
            current_act_label = act
            adv_lines.append(f'<div class="progress-act-header">Act {act}</div>')

        if num < current_adv:
            # Completed — link to adventure page, synopsis displayed below
            summary = adventure_summaries.get(str(num), "")
            summary_html = f'<br><span class="dimmed" style="margin-left:2ch;font-size:0.9em;">{summary}</span>' if summary else ""
            adv_lines.append(
                f'<div class="adv-row">'
                f'<a href="/campaigns/adventures/{num:02d}/">'
                f'{num:02d}. {name}</a>'
                f'{summary_html}'
                f'</div>'
            )
        elif num == current_adv:
            # In progress
            adv_lines.append(
                f'<div class="adv-row">'
                f'<a href="/campaigns/adventures/{num:02d}/">'
                f'{num:02d}. {name}</a>'
                f' <span class="progress-status-active">active</span>'
                f'</div>'
            )
        elif num == current_adv + 1:
            # Teaser — show name but no link
            adv_lines.append(
                f'<div class="adv-row dimmed">'
                f'{num:02d}. {name}'
                f'</div>'
            )
        else:
            # Future — hidden
            adv_lines.append(
                f'<div class="adv-row dimmed">'
                f'{num:02d}. ???'
                f'</div>'
            )

    adv_list = "\n".join(adv_lines)

    # Story so far
    story_summary = state.get("story_summary", "")
    story_html = ""
    if story_summary:
        story_html = f'<div class="section-title">Story So Far</div><p>{story_summary}</p>'

    # Party block
    party = state.get("party", {})
    party_html = ""
    if party:
        levels = []
        for name, info in party.items():
            cls = info.get("class", "")
            sub_match = re.search(r'\(([^)]+)\)', cls) if cls else None
            base_class = cls.split("(")[0].strip().rstrip("0123456789 ") if cls else ""
            short_class = sub_match.group(1) if sub_match else base_class
            if short_class:
                levels.append(f"{name} — {short_class} (lvl {info.get('level', 1)})")
            else:
                levels.append(f"{name} (lvl {info.get('level', 1)})")
        location = state.get("current_location", "")
        loc_html = (f'<p style="margin-top:0.6rem;color:var(--dim);font-size:0.85em;">'
                    f'Location: {location}</p>' if location else "")
        party_html = (
            '<div class="state-block">'
            '<h4>The Party</h4>'
            '<ul>' + "".join(f"<li>{l}</li>" for l in levels) + '</ul>'
            f'{loc_html}'
            '</div>'
        )

    # Just the overall progress bar on the campaigns page — the per-adventure
    # detail is shown in the Adventures list below, so no need to duplicate it.
    overall_bar = render_overall_bar(sessions_done)

    content = (
        f'<h1>{CAMPAIGN_NAME}</h1>'
        f'<p class="dimmed">{SITE_SUBTITLE}</p>'
        f'<hr>'
        f'{story_html}'
        f'{party_html}'
        f'<hr>'
        f'<div class="section-title">Campaign Progress</div>'
        f'{overall_bar}'
        f'<hr>'
        f'<div class="section-title">Adventures</div>'
        f'{adv_list}'
    )
    return render_page(
        CAMPAIGN_NAME,
        content,
        active_nav="campaigns",
    )


def build_adventure_page(adv: dict, state: dict, sessions: list[dict],
                         wiki_slugs: set[str] = None) -> str:
    """Build /campaigns/adventures/NN/index.html — session report + transcript link."""
    num = adv["num"]
    name = adv["name"]
    num_str = f"{num:02d}"

    # Find the session for this adventure (1:1 mapping)
    session_num = num
    adv_session = next((s for s in sessions if s["num"] == session_num), None)

    if adv_session:
        # Render session report directly on the adventure page
        raw = adv_session["raw"]
        if wiki_slugs:
            raw = resolve_wiki_links(raw, wiki_slugs)
        body_html = md_to_html(raw)

        transcript_link = (
            f'<div class="notice">Narrative session report &mdash; '
            f'<a href="/campaigns/sessions/{num_str}/transcript/">'
            f'read the raw transcript &rarr;</a></div>'
        )

        nav = (
            f'<p><a href="/campaigns/">&laquo; Back to campaign</a></p>'
        )

        content = transcript_link + body_html + nav
    else:
        # No session yet (adventure in progress or upcoming)
        current_adv = state.get("current_adventure", 1)
        if num == current_adv:
            status = "In Progress"
        else:
            status = "Upcoming"
        content = (
            f'<h1>Adventure {num}: {name}</h1>'
            f'<p class="dimmed">Act {adv.get("act", "?")} &mdash; Level {adv.get("level", "?")}'
            f' &mdash; {status}</p>'
            f'<p class="dimmed">No session report yet.</p>'
            f'<p><a href="/campaigns/">&laquo; Back to campaign</a></p>'
        )

    return render_page(
        f"Adventure {num}: {name}",
        content,
        active_nav="campaigns",
    )


def build_session_page(
    session: dict,
    wiki_slugs: set[str],
    prev_num: int | None,
    next_num: int | None,
) -> str:
    """Build /campaigns/run-N/sessions/NN/index.html — session report."""
    num = session["num"]
    num_str = f"{num:02d}"

    # Resolve [[links]] before markdown conversion
    raw = resolve_wiki_links(session["raw"], wiki_slugs)
    body_html = md_to_html(raw)

    campaign_url = f"/campaigns/"
    nav_html = session_nav(
        prev_num, next_num,
        campaign_url=campaign_url,
        prev_url_tmpl=f"/campaigns/sessions/{{}}/" ,
        next_url_tmpl=f"/campaigns/sessions/{{}}/",
    )

    notice = (
        f'<div class="notice">Narrative session report &mdash; '
        f'<a href="/campaigns/sessions/{num_str}/transcript/">'
        f'read the raw transcript &rarr;</a></div>'
    )

    breadcrumb = (
        f'<a href="/campaigns/">Campaigns</a> / '
        f'<span>Session {num_str}</span>'
    )

    content = nav_html + notice + body_html + nav_html
    return render_page(
        session["title"],
        content,
        breadcrumb=breadcrumb,
        active_nav="campaigns",
    )


def build_transcript_page(session: dict, prev_num: int | None, next_num: int | None) -> str:
    """Build /campaigns/sessions/NN/transcript/index.html."""
    num = session["num"]
    num_str = f"{num:02d}"

    body_html = md_to_html(session["transcript_raw"])

    nav_html = session_nav(
        prev_num, next_num,
        campaign_url=f"/campaigns/",
        prev_url_tmpl=f"/campaigns/sessions/{{}}/transcript/",
        next_url_tmpl=f"/campaigns/sessions/{{}}/transcript/",
    )

    notice = (
        f'<div class="notice">Raw gameplay transcript &mdash; '
        f'<a href="/campaigns/sessions/{num_str}/">'
        f'&larr; read the session report instead</a></div>'
    )

    breadcrumb = (
        f'<a href="/campaigns/">Campaigns</a> / '
        f'<a href="/campaigns/sessions/{num_str}/">Session {num_str}</a> / '
        f'<span>Transcript</span>'
    )

    content = nav_html + notice + f'<div class="transcript-body">{body_html}</div>' + nav_html
    return render_page(
        f"Session {num_str} — Transcript",
        content,
        breadcrumb=breadcrumb,
        active_nav="campaigns",
    )


def build_wiki_index(wiki_entries: list[dict]) -> str:
    """Build /wiki/index.html — alphabetical index of all entries."""
    sorted_entries = sorted(wiki_entries, key=lambda e: e["name"].lower())

    links_html = ""
    if sorted_entries:
        links_html = '<div class="wiki-index">'
        for e in sorted_entries:
            links_html += (
                f'<a href="/wiki/{e["slug"]}/">{e["name"]}</a>'
            )
        links_html += '</div>'
    else:
        links_html = '<p class="dimmed">No wiki entries yet.</p>'

    count = len(sorted_entries)
    content = (
        f'<h1>Wiki</h1>'
        f'<p class="dimmed">{count} entr{"y" if count == 1 else "ies"} — '
        f'characters, locations, factions, items, and lore from {SITE_TITLE}.</p>'
        f'<hr>'
        f'{links_html}'
    )
    return render_page("Wiki", content, active_nav="wiki")


def build_wiki_entry_page(entry: dict, wiki_slugs: set[str]) -> str:
    """Build /wiki/slug/index.html — individual wiki entry."""
    # Wiki entries don't have a # header — add one from the filename
    raw_content = entry["raw"]

    # Strip a leading h1 if the entry already has one (some might)
    raw_content = re.sub(r'^#\s+.+\n', '', raw_content, count=1).lstrip()

    resolved = resolve_wiki_links(raw_content, wiki_slugs)
    body_html = md_to_html(resolved)

    breadcrumb = f'<a href="/wiki/">Wiki</a> / <span>{entry["name"]}</span>'
    content = (
        f'<h1>{entry["name"]}</h1>'
        f'<p class="wiki-entry-meta dimmed">Laternia Wiki</p>'
        f'<hr>'
        f'{body_html}'
    )
    return render_page(entry["name"], content, breadcrumb=breadcrumb, active_nav="wiki")


def build_readme_page(state: dict, sessions_done: int) -> str:
    """Build /readme/index.html — auto-generated project readme."""
    party = state.get("party", {})
    session_num = state.get("session_number", 0)
    current_adv = state.get("current_adventure_name", "—")

    party_rows = ""
    for name, info in party.items():
        party_rows += f"<li>{name}, Level {info.get('level', 1)}</li>"

    agents = [
        ("Dungeon Master",   "Narrates scenes, runs NPCs, drives the story forward."),
        ("Cora Flint",       "PC — Artificer. Pragmatic, ledger-keeping, frost spells."),
        ("Garrick Kade",     "PC — Fighter. Half-orc, maul, history with Kregg."),
        ("Prof. Mercer",     "PC — Wizard. Academic, excitable, catalogues everything."),
        ("Rules Keeper",     "Adjudicates contested rolls and combat outcomes."),
        ("Scribe",           "Writes the narrative session report after each session."),
        ("Wiki Keeper",      "Extracts named entities and writes encyclopedia entries."),
        ("Editor",           "Fact-checks the Scribe and Wiki Keeper against the transcript."),
        ("Lorekeeper",       "NPC name consistency, encyclopedic rewrites, deduplication."),
    ]
    agent_rows = "".join(
        f"<li><strong>{name}</strong> — {desc}</li>"
        for name, desc in agents
    )

    content = f"""<h1>Readme</h1>
<p class="dimmed">What this is and how it works.</p>
<hr>

<h2>What is Laternia?</h2>
<p>
Laternia is an autonomous AI Dungeons &amp; Dragons campaign. Every session
is played entirely by large language models — a DM agent narrates, three PC
agents respond, a Rules Keeper adjudicates rolls, and a suite of post-session
agents write the narrative, maintain the wiki, and fact-check everything.
No human plays during a run. Sessions are scheduled to run once per day.
</p>

<h2>Current Campaign: {CAMPAIGN_NAME}</h2>
<div class="state-block">
  <h4>Status</h4>
  <ul>
    <li>Sessions completed: {sessions_done}</li>
    <li>Current adventure: {current_adv}</li>
    {party_rows}
  </ul>
</div>

<h2>The Agent Pipeline</h2>
<p>Each session runs the following agents in sequence:</p>
<div class="state-block">
  <h4>Per Session</h4>
  <ul>{agent_rows}</ul>
</div>

<h2>Technical Stack</h2>
<ul>
  <li><strong>Framework:</strong> CrewAI (multi-agent orchestration)</li>
  <li><strong>LLMs:</strong> DeepSeek (all gameplay and post-session agents)</li>
  <li><strong>Site:</strong> Custom Python static generator &rarr; GitHub &rarr; Vercel</li>
  <li><strong>Scheduling:</strong> Claude Code scheduled tasks (one session/day)</li>
</ul>

<h2>Source</h2>
<p>
This is a digital art project by <a href="https://maxcapa.city">Max Capacity</a>.
The infrastructure is built with Claude Code (Anthropic).
The campaign world, adventure structure, and agent prompts are hand-authored.
The sessions are fully autonomous.
</p>
"""
    return render_page("Readme", content, active_nav="readme")


def build_404_page() -> str:
    """Build a custom 404 error page (docs/404.html)."""
    skull_art = (
        '    =+@@@@@@@+ =.  *-#%=*#@@% :%@#%#+  .      ++%:++-%= ++:  @%=#.  #@=+=       \n'
        '    :=. .@#   :--  ..--    -+ +=.              *%%#  -:--    #*#*  : =- -       \n'
        '    :+     -..#+.  @@@#- .        .+#%%%%#+-   %%%#+==          *@@= ===:       \n'
        '#+:  +=*#:=#=++:    .         :#@@@@@@@@@@@@@@=.-*+:.      :--. .. .=:    .+*#%%\n'
        '@@@#    ##%*     .=-:::.     #@@@@#@@@@@@@@@@@@*      .*@@@@@@@@@@+     *@@@@@@@\n'
        '@%+.*         *@@@@@@@@@@%-  %@#@@@#@@@@@@@@@@@@     +@@@@@@@@@@@@@@*  :-@@@%@@@\n'
        '- :++       -#@@@@@@@@@@@@@# :@#*=:%%====*%@@%#%#-   %+:.:@@@@@@@@%. * :. :#   *\n'
        '+  .        =+#@@#@@@@@@@%##= :-+%*@      @@     .  @*    *%%   :@. +*  %*:%*++#\n'
        '    :=++++=  ::=:%:   :@@    +   -@@#+++*@@* .. -  -##+##   %    *+*=    =:     \n'
        '-@@@@@@@@@@@+ -*-%* .:@+  #*+#-  #:  =@@@   =:-*:    .#@%*=#+#%*%-     :.::.    \n'
        '@@@@@@@@@@%.++. :*#+*@@: .@@    -@@= =%@@%*#*       *#*=+@## ..:.   #@@@@@@@@@@*\n'
        '*@@@@@@...-=.-+  +#  =*%%%%+     .#@%#++=%##-       +=  ..        -@@@@@@@@@@@@@\n'
        ' =@*-@=    # :-   =*%%%%%%#*.      .%@@@%%++    +#@@@@@@@@@%=    .:..@@@%@@@#: @\n'
        ' +@   @%+++*=.       -*#*=-.          -**++:  *@@@@@@@@@@@@@@@#. *   :%.   -+ #*\n'
        '@@@#--@+                  .-%@@@@@@%*.       -*++#@@@@@@@@@@%=:*++#%* +*=::-.## \n'
        '#@#@@%+.=*##%%%##*-     %@@@@@@@@@@@@@@%    -*+*#@@@@@@@@@*#:  -* :  -  *#+=:#* \n'
        '#=    :@@@@@@@@@@@@%+  #@@@@@@@@@@@@@@@@@+  +     .%@@@%+*+*- .-: ...        %% \n'
        '%#%+::++=#@@@@*@@@@+#* +@##@@*@@@@@@@@@@@@ .:     :#@@+     += #@@@@@@@@@*   @%@\n'
        '@@@@@@@*:%@@#-*@-..%#.  %@*::%*:...+@@=+*#==#+:=+#* :-=-    =. @@@%%%%-#@@@+ ##+\n'
        '-: -@%.= .*+..@%   %  =  +***@     #@#    +-#@=-*=   -*+**#%+-  @%    @.:@@@  :*\n'
        ':  +=   =  -.=#@%*%% *=    :+%%##%@%. -+=== :== :-=::*= .**#*+ .  @#**%#.-@# = .\n'
        '-#@% .#+=. *#%:  =%#%%*      *  =@@:  #: -    .++*#@@*+-:.    +@:*@@. . =*+  .  \n'
        ' .*%###=   -@@@%#*+*###.    -@@*=+#%@%@        :.=*+:*:..*:   **++-#+#%+.       \n'
        '@ .@%#-.     :+##%@@@*         *%%%##=.         ::-=-+-+**.   .@%@@#*+   -%@@@@@\n'
        '@@.=+:.               .=*###*-    ::  -*%@@@@@#-..#@#++=    *@%=::      @@@@@@@@\n'
        ' *.    -*###+.     -%@@@@@@@@@@@*    ++@@@@@@@@@@*        :#- #@@@#+=  +  +@-   \n'
        '+*    @@@@@@@%*   @@@@@@@@@@@@@@@%-  +:=@@@@@+++*:#     +: %+.#+*%%#+: *=*. *#=+\n'
        '-    +- .%. #-*  +@@@@@@@@*=@@-  +#   =+   ##   #-:      .:=-+-          *@+%@%.\n'
        '-    **#    #:    %@@@@#*+ :@#     #   -=:++ *#++- :***+:      .=*+:      #%%%*-\n'
        '   .*@@@*##=:      =:=#--:*%%+@%#*#@+      +***  =+@@@@@@%*. +@@@@@@@@@#- -+-.'
    )
    content = (
        f'<pre class="ascii-art">{skull_art}</pre>'
        '<h1>404</h1>'
        '<p class="dimmed">You have died of dysentery.</p>'
        '<hr>'
        '<p><a href="/">Return to the campaign &rarr;</a></p>'
    )
    return render_page("404 — Not Found", content)


def build_changelog_page() -> str:
    """Build /changelog/index.html — rendered CHANGELOG.md."""
    if CHANGELOG_FILE.exists():
        raw = CHANGELOG_FILE.read_text(encoding="utf-8")
        body_html = md_to_html(raw)
    else:
        body_html = '<p class="dimmed">No changelog yet.</p>'

    content = (
        '<h1>Changelog</h1>'
        '<p class="dimmed">System versions, additions, and fixes.</p>'
        '<hr>'
        + body_html
    )
    return render_page("Changelog", content, active_nav="changelog")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_sessions() -> list[dict]:
    """Load all session reports and transcripts from output/sessions/."""
    sessions = []

    if not SESSIONS_DIR.exists():
        return sessions

    for report_file in sorted(SESSIONS_DIR.glob("session_[0-9][0-9].md")):
        m = re.match(r"session_(\d+)\.md$", report_file.name)
        if not m:
            continue
        num = int(m.group(1))

        raw = report_file.read_text(encoding="utf-8")

        # Extract title from first # heading
        title_m = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else f"Session {num:02d}"
        # Strip the leading "Session N: " prefix for cleanliness
        title = re.sub(r"^Session\s+\d+[:\-–—]\s*", "", title).strip() or title

        # Load transcript if it exists
        transcript_file = SESSIONS_DIR / f"session_{num:02d}_transcript.md"
        transcript_raw = (
            transcript_file.read_text(encoding="utf-8")
            if transcript_file.exists() else ""
        )

        sessions.append({
            "num":            num,
            "title":          title,
            "raw":            raw,
            "transcript_raw": transcript_raw,
        })

    return sessions


def load_wiki() -> list[dict]:
    """Load all wiki entries from output/wiki/."""
    entries = []

    if not WIKI_DIR.exists():
        return entries

    for wiki_file in sorted(WIKI_DIR.glob("*.md")):
        name = wiki_file.stem  # filename without extension = display name
        raw = wiki_file.read_text(encoding="utf-8")
        entries.append({
            "name": name,
            "slug": slugify(name),
            "raw":  raw,
        })

    return entries


def load_state() -> dict:
    """Load campaign_state.json."""
    try:
        return json.loads(CAMPAIGN_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"session_number": 0, "party": {}, "current_location": ""}


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build_site() -> None:
    """Build the entire static site into docs/."""
    print("[Site] Building static site...")
    start = datetime.now()

    # --- Load data ---
    state       = load_state()
    adventures  = parse_campaign_arc()
    sessions    = load_sessions()
    wiki        = load_wiki()
    wiki_slugs  = {e["slug"] for e in wiki}

    sessions_done = len(sessions)

    # --- Wipe and recreate docs/ ---
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    # --- Assets ---
    assets_dir = DOCS_DIR / "assets"
    assets_dir.mkdir()
    (assets_dir / "style.css").write_text(CSS, encoding="utf-8")

    def write(path: Path, html: str) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.html").write_text(html, encoding="utf-8")

    # --- Homepage ---
    write(DOCS_DIR, build_homepage(state, adventures, sessions, wiki_slugs))

    # --- Campaigns page (progress + session list) ---
    campaigns_dir = DOCS_DIR / "campaigns"
    write(campaigns_dir, build_campaigns_page(state, adventures, sessions))

    # --- Adventure pages ---
    current_adv = state.get("current_adventure", 1)
    for adv in adventures:
        if adv["num"] <= current_adv:
            adv_dir = campaigns_dir / "adventures" / f"{adv['num']:02d}"
            write(adv_dir, build_adventure_page(adv, state, sessions, wiki_slugs))

    # --- Session pages ---
    for i, session in enumerate(sessions):
        num_str = f"{session['num']:02d}"
        prev_num = sessions[i - 1]["num"] if i > 0 else None
        next_num = sessions[i + 1]["num"] if i < len(sessions) - 1 else None

        sess_dir = campaigns_dir / "sessions" / num_str
        write(sess_dir, build_session_page(session, wiki_slugs, prev_num, next_num))

        if session["transcript_raw"]:
            write(
                sess_dir / "transcript",
                build_transcript_page(session, prev_num, next_num),
            )

    # --- Wiki ---
    write(DOCS_DIR / "wiki", build_wiki_index(wiki))
    for entry in wiki:
        write(DOCS_DIR / "wiki" / entry["slug"], build_wiki_entry_page(entry, wiki_slugs))

    # --- Readme + Changelog ---
    write(DOCS_DIR / "readme",    build_readme_page(state, sessions_done))
    write(DOCS_DIR / "changelog", build_changelog_page())

    # --- 404 page (flat file — Vercel serves docs/404.html for missing routes) ---
    (DOCS_DIR / "404.html").write_text(build_404_page(), encoding="utf-8")

    # --- Vercel routing config ---
    # Tells Vercel to serve index.html for every clean URL
    vercel_config = {
        "cleanUrls": True,
        "trailingSlash": True,
    }
    (DOCS_DIR / "vercel.json").write_text(
        json.dumps(vercel_config, indent=2), encoding="utf-8"
    )

    # --- Summary ---
    elapsed = (datetime.now() - start).total_seconds()
    adv_page_count = sum(1 for a in adventures if a["num"] <= current_adv)
    page_count = (
        1                     # homepage
        + 1                   # campaigns page
        + adv_page_count      # adventure pages
        + len(sessions) * 2   # report + transcript per session
        + 1                   # wiki index
        + len(wiki)           # wiki entries
        + 2                   # readme + changelog
    )
    print(
        f"[Site] Built {page_count} pages "
        f"({sessions_done} sessions, {len(wiki)} wiki entries) "
        f"in {elapsed:.1f}s -> docs/"
    )


if __name__ == "__main__":
    build_site()
