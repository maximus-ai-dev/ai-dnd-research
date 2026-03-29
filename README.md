# Constructive Adversarial Architecture

**Overcoming Cooperation Bias in Autonomous Multi-Agent Narrative Systems Through 180+ Sessions of AI Dungeons & Dragons**

## What This Is

An autonomous D&D campaign system where 8+ AI agents play Dungeons & Dragons together. A DM narrates the world. Three player characters make decisions. A Rules Keeper enforces mechanics. Post-session agents write narratives, build a wiki, and publish to a live website. The whole thing runs unattended on DeepSeek for about $17 per 20-session campaign.

The system works. The problem is that the DM refuses to let anything fight.

This repository contains the complete system code, all 20 adventure files, and the full dataset from nine controlled runs (180+ sessions) testing six categories of fixes for cooperation bias. The accompanying paper describes the findings.

## The Paper

[Read the full paper](paper.md)

**Key finding:** Guard rails (instructions that prohibit behavior) fail. Guide rails (structural constraints that produce behavior) work. Telling the DM "don't befriend enemies" doesn't work. Giving the enemy its own AI agent that attacks independently does.

## Repository Structure

```
code/               System code (all agents, session loop, pipeline)
  agents.py         Agent definitions (DM, PCs, Rules Keeper, enemy agents)
  session.py        Session orchestrator and exchange loop
  enemy_encounters.py  Enemy agent configurations for boss encounters
  run.py            Entry point
  config.py         Configuration (API keys loaded from .env)
  tools.py          CrewAI tool definitions
  leveling.py       Level-up stat blocks and features
  site_builder.py   Static site generator

adventures/         All 20 adventure files (levels 1-20, four acts)

wiki_seed/          Pre-seeded canonical wiki entries

data/               Archived output from all 9 runs
  60-session-run/   Run 1: baseline (60 sessions, 3 per adventure)
  20-session-run/   Run 2: baseline (20 sessions, 1 per adventure)
  run3-groupA/      Run 3: pipeline fixes
  run4-groupAB/     Run 4: + adventure tags
  run5-groupABD/    Run 5: + mechanical forcing
  run6-groupABDE/   Run 6: + enemy agents + PC triggers
  run7-target-lock-session-end/  Run 7: + target lock + session completion
  run8-polish-pass/ Run 8: + pre-seeded wiki + combat fixes
  run9-final-test/  Run 9: + adventure redesign + position fixes

paper.md            The full research paper
```

## How to Run

1. Clone this repository
2. Install Python 3.11+ and create a virtual environment
3. Install dependencies: `pip install crewai litellm python-dotenv markdown`
4. Copy `code/.env.template` to `code/.env` and add your DeepSeek API key
5. Place adventure files and campaign state in the expected paths (see config.py)
6. Run: `python code/run.py --all-deepseek`

Chain multiple sessions: `python code/run.py --all-deepseek && python code/run.py --all-deepseek`

A complete 20-session campaign takes 8-12 hours and costs ~$17 on DeepSeek.

## The Dataset

The `data/` directory contains the complete output from nine campaign runs:

- **Session logs** (raw gameplay transcripts)
- **Session narratives** (polished prose reports)
- **Editor reviews** (content invention and missing content flags)
- **Lorekeeper reviews** (wiki consistency checks)
- **Wiki entries** (accumulated world knowledge)
- **Campaign state** (JSON snapshots of party, inventory, progress)

Each run tested specific independent variables. The run-by-run methodology is described in Section 3 of the paper. Every code change is traceable to a specific git commit in the original development repository.

## Key Numbers

- 9 controlled runs
- 180+ total sessions
- $155.39 total API cost
- 11 documented avoidance vectors
- Boss fight success rate: 25% (baseline) to 100% (Run 7)
- Stealth format cooperation-proof rate: 100% (17/17 tests)
- PC behavioral trigger compliance: 95%+

## Cost

All runs used DeepSeek at approximately $0.15-0.25 per session. The entire dataset behind this paper was generated for under $160. Running the same campaign on Claude or GPT-4 would cost an estimated 10-50x more per session.

## License

MIT

## Attribution

System design and experiment methodology by the author. Code development and paper drafting assisted by Claude Opus 4.6 (Anthropic). All gameplay sessions run on DeepSeek.
