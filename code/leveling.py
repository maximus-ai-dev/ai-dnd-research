"""
leveling.py — D&D 5e milestone leveling for the AI campaign.

Handles automatic level-ups when adventures complete. Updates character stats
in campaign_state.json so the PC agents always have current information.

Design:
  - HP uses the "average" method (half hit die + 1 + CON mod), standard in 5e
  - Proficiency bonus follows the standard 5e table
  - Class features, spells, and ASIs are stored per-level per-class
  - The full stat block is stored in campaign_state.json under each PC's entry
  - agents.py reads these stats dynamically instead of hardcoding them
"""


# ---------------------------------------------------------------------------
# Proficiency bonus by level (standard 5e)
# ---------------------------------------------------------------------------
def proficiency_bonus(level: int) -> int:
    if level <= 4:
        return 2
    elif level <= 8:
        return 3
    elif level <= 12:
        return 4
    elif level <= 16:
        return 5
    else:
        return 6


# ---------------------------------------------------------------------------
# Class data: hit die, CON mod, and per-level features/spells
# ---------------------------------------------------------------------------
# Each class entry contains:
#   hit_die: size of hit die
#   con_mod: constitution modifier (for HP calculation)
#   hp_per_level: average HP gained per level (half hit die + 1 + CON mod)
#   levels: dict of level -> dict with keys:
#     features: list of new class features gained
#     cantrips: list of new cantrips (if any)
#     spells: list of new/changed spell info
#     spell_slots: string describing total spell slots at this level
#     notes: any other relevant info for the DM/PC

CLASS_DATA = {
    "Cora Flint": {
        "hit_die": 8,
        "con_mod": 2,
        "hp_per_level": 7,  # (8/2 + 1) + 2
        "base_hp": 10,
        "levels": {
            1: {
                "class_string": "Artificer (Alchemist) 1",
                "features": ["Magical Tinkering", "Spellcasting"],
                "cantrips": ["Mending", "Ray of Frost"],
                "spells": ["Cure Wounds", "Detect Magic"],
                "spell_slots": "2 first-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 10, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 16(+3) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +4, INT +5. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            2: {
                "class_string": "Artificer (Alchemist) 2",
                "features": ["Infuse Item (2 infusions known, 2 active)"],
                "cantrips": [],
                "spells": ["Healing Word"],
                "spell_slots": "2 first-level slots",
                "infusions": [
                    "Enhanced Arcane Focus (+1 to spell attack rolls)",
                    "Repeating Shot (turns crossbow into +1 magic weapon, ignores loading)",
                    "Homunculus Servant (tiny construct companion)",
                    "Bag of Holding",
                ],
                "notes": "Choose 2 infusions. Can change infusions on long rest.",
                "stats": (
                    "AC 14 (studded leather), HP 17, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 16(+3) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +4, INT +5. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            3: {
                "class_string": "Artificer (Alchemist) 3",
                "features": [
                    "Alchemist Specialist — Experimental Elixir (create 1 free elixir on long rest)",
                    "Alchemist Spells: Healing Word, Ray of Sickness (always prepared)",
                    "The Right Tool for the Job (conjure artisan's tools)",
                ],
                "cantrips": [],
                "spells": ["Healing Word (always prepared)", "Ray of Sickness (always prepared)"],
                "spell_slots": "3 first-level slots",
                "elixir_options": [
                    "Healing (2d4+INT HP)",
                    "Swiftness (+10 speed for 1 hour)",
                    "Resilience (+1 AC for 10 minutes)",
                    "Boldness (advantage on saves vs frightened for 1 minute)",
                    "Flight (10ft flying speed for 10 minutes)",
                    "Transformation (alter self for 10 minutes)",
                ],
                "stats": (
                    "AC 14 (studded leather), HP 24, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 16(+3) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +4, INT +5. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            4: {
                "class_string": "Artificer (Alchemist) 4",
                "features": [
                    "ASI: +2 INT (INT becomes 18, +4 modifier)",
                ],
                "cantrips": ["Acid Splash"],
                "spells": [],
                "spell_slots": "3 first-level slots",
                "notes": "INT increases to 18 (+4). Spell save DC becomes 14. Spell attack becomes +6.",
                "stats": (
                    "AC 14 (studded leather), HP 31, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +4, INT +6. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            5: {
                "class_string": "Artificer (Alchemist) 5",
                "features": [
                    "Alchemical Savant (+INT mod to healing/damage from alchemist spells)",
                    "Alchemist Spells: Flaming Sphere, Melf's Acid Arrow (always prepared)",
                ],
                "cantrips": [],
                "spells": ["Flaming Sphere (always prepared)", "Melf's Acid Arrow (always prepared)", "Web"],
                "spell_slots": "4 first-level, 2 second-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 38, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +5, INT +7. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            6: {
                "class_string": "Artificer (Alchemist) 6",
                "features": [
                    "Tool Expertise (double proficiency bonus on tool checks)",
                ],
                "cantrips": [],
                "spells": ["Protection from Poison"],
                "spell_slots": "4 first-level, 2 second-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 45, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +5, INT +7. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            7: {
                "class_string": "Artificer (Alchemist) 7",
                "features": [
                    "Flash of Genius (reaction: add INT mod to ability check or save within 30ft, INT uses/LR)",
                ],
                "cantrips": [],
                "spells": ["Aid"],
                "spell_slots": "4 first-level, 3 second-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 52, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 12(+1) CHA 8(-1)\n"
                    "Saves: CON +5, INT +7. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            8: {
                "class_string": "Artificer (Alchemist) 8",
                "features": [
                    "ASI: +2 WIS (WIS becomes 14, +2 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level slots",
                "notes": "WIS increases to 14 (+2).",
                "stats": (
                    "AC 14 (studded leather), HP 59, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +5, INT +7. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            9: {
                "class_string": "Artificer (Alchemist) 9",
                "features": [
                    "Arcane Jolt (2d6 heal or damage, INT uses/LR)",
                    "Alchemist Spells: Mass Healing Word, Stinking Cloud (always prepared)",
                ],
                "cantrips": [],
                "spells": ["Mass Healing Word (always prepared)", "Stinking Cloud (always prepared)", "Revivify"],
                "spell_slots": "4 first-level, 3 second-level, 2 third-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 66, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +6, INT +8. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            10: {
                "class_string": "Artificer (Alchemist) 10",
                "features": [
                    "Magic Item Adept (attune up to 4 magic items, craft common/uncommon in quarter time)",
                    "Infusions: 8 known, 4 active",
                ],
                "cantrips": [],
                "spells": ["Dispel Magic"],
                "spell_slots": "4 first-level, 3 second-level, 2 third-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 73, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +6, INT +8. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            11: {
                "class_string": "Artificer (Alchemist) 11",
                "features": [
                    "Spell-Storing Item (store a 1st/2nd-level artificer spell in an item, 2xINT uses)",
                ],
                "cantrips": [],
                "spells": ["Haste"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 80, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 18(+4) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +6, INT +8. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            12: {
                "class_string": "Artificer (Alchemist) 12",
                "features": [
                    "ASI: +2 INT (INT becomes 20, +5 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level slots",
                "notes": "INT increases to 20 (+5). Spell save DC becomes 17. Spell attack becomes +9.",
                "stats": (
                    "AC 14 (studded leather), HP 87, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +6, INT +9. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            13: {
                "class_string": "Artificer (Alchemist) 13",
                "features": [
                    "Alchemist Spells: Death Ward, Freedom of Movement (always prepared)",
                ],
                "cantrips": [],
                "spells": ["Death Ward (always prepared)", "Freedom of Movement (always prepared)", "Fabricate"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 1 fourth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 94, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +7, INT +10. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            14: {
                "class_string": "Artificer (Alchemist) 14",
                "features": [
                    "Magic Item Savant (attune up to 5 magic items, ignore class/race/level requirements)",
                    "Infusions: 10 known, 5 active",
                ],
                "cantrips": [],
                "spells": ["Stoneskin"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 1 fourth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 101, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +7, INT +10. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            15: {
                "class_string": "Artificer (Alchemist) 15",
                "features": [
                    "Restorative Reagents (free Lesser Restoration when creating elixir, elixirs give temp HP = 2d6+INT)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 2 fourth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 108, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +7, INT +10. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            16: {
                "class_string": "Artificer (Alchemist) 16",
                "features": [
                    "ASI: Feat (War Caster — advantage on CON saves for concentration, somatic with hands full, opportunity attack cantrip)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 2 fourth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 115, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +7, INT +10. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            17: {
                "class_string": "Artificer (Alchemist) 17",
                "features": [
                    "Alchemist Spells: Cloudkill, Raise Dead (always prepared)",
                ],
                "cantrips": [],
                "spells": ["Cloudkill (always prepared)", "Raise Dead (always prepared)", "Greater Restoration"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 1 fifth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 122, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +8, INT +11. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            18: {
                "class_string": "Artificer (Alchemist) 18",
                "features": [
                    "Magic Item Master (attune up to 6 magic items)",
                    "Infusions: 12 known, 6 active",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 1 fifth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 129, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 14(+2) CHA 8(-1)\n"
                    "Saves: CON +8, INT +11. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            19: {
                "class_string": "Artificer (Alchemist) 19",
                "features": [
                    "ASI: +2 WIS (WIS becomes 16, +3 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level slots",
                "notes": "WIS increases to 16 (+3).",
                "stats": (
                    "AC 14 (studded leather), HP 136, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 16(+3) CHA 8(-1)\n"
                    "Saves: CON +8, INT +11. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
            20: {
                "class_string": "Artificer (Alchemist) 20",
                "features": [
                    "Soul of Artifice (+1 to all saving throws per attuned magic item)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level slots",
                "stats": (
                    "AC 14 (studded leather), HP 143, Speed 30ft.\n"
                    "STR 10(+0) DEX 14(+2) CON 14(+2) INT 20(+5) WIS 16(+3) CHA 8(-1)\n"
                    "Saves: CON +8, INT +11. Skills: Insight, Investigation, Medicine, Perception.\n"
                    "Tools: Alchemist's Supplies, Cook's Utensils, Tinker's Tools, Thieves' Tools."
                ),
            },
        },
    },
    "Garrick Kade": {
        "hit_die": 10,
        "con_mod": 3,
        "hp_per_level": 9,  # (10/2 + 1) + 3
        "base_hp": 13,
        "levels": {
            1: {
                "class_string": "Fighter (Rune Knight) 1",
                "features": [
                    "Fighting Style: Great Weapon Fighting",
                    "Second Wind (bonus action, 1d10+1 HP)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 13, Speed 30ft.\n"
                    "STR 16(+3) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +5, CON +5. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools.\n"
                    "Weapons: Maul (2d6+3), two handaxes (1d6+3)."
                ),
            },
            2: {
                "class_string": "Fighter (Rune Knight) 2",
                "features": [
                    "Action Surge (one extra action per short rest)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 22, Speed 30ft.\n"
                    "STR 16(+3) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +5, CON +5. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools.\n"
                    "Weapons: Maul (2d6+3), two handaxes (1d6+3)."
                ),
            },
            3: {
                "class_string": "Fighter (Rune Knight) 3",
                "features": [
                    "Rune Knight: Rune Carver — inscribe 2 runes on gear (choose from list)",
                    "Giant's Might (bonus action: become Large for 1 min, +1d6 damage, advantage on STR checks, prof uses/LR)",
                ],
                "rune_options": [
                    "Cloud Rune: redirect attack to another target (reaction, 1/SR)",
                    "Fire Rune: extra 2d6 fire + restrain on hit (1/SR)",
                    "Frost Rune: +2 to STR/CON ability checks, bonus action for ally +2 (1/SR)",
                    "Stone Rune: charm a creature within 30ft (reaction, 1/SR)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 31, Speed 30ft.\n"
                    "STR 16(+3) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +5, CON +5. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+3), two handaxes (1d6+3)."
                ),
            },
            4: {
                "class_string": "Fighter (Rune Knight) 4",
                "features": [
                    "ASI: +2 STR (STR becomes 18, +4 modifier)",
                ],
                "notes": "STR increases to 18 (+4). Melee attacks become +6 to hit, Maul 2d6+4, handaxes 1d6+4.",
                "stats": (
                    "AC 16 (chain mail), HP 40, Speed 30ft.\n"
                    "STR 18(+4) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +6, CON +5. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+4), two handaxes (1d6+4)."
                ),
            },
            5: {
                "class_string": "Fighter (Rune Knight) 5",
                "features": [
                    "Extra Attack (2 attacks per Attack action)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 49, Speed 30ft.\n"
                    "STR 18(+4) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +7, CON +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+4 x2), two handaxes (1d6+4)."
                ),
            },
            6: {
                "class_string": "Fighter (Rune Knight) 6",
                "features": [
                    "ASI: Feat (Great Weapon Master — -5 to hit for +10 damage, bonus action attack on crit/kill)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 58, Speed 30ft.\n"
                    "STR 18(+4) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +7, CON +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+4 x2), two handaxes (1d6+4)."
                ),
            },
            7: {
                "class_string": "Fighter (Rune Knight) 7",
                "features": [
                    "Runic Shield (reaction: force reroll of attack roll against ally within 60ft, prof uses/LR)",
                ],
                "notes": "3 runes known.",
                "rune_options": [
                    "Cloud Rune: redirect attack to another target (reaction, 1/SR)",
                    "Fire Rune: extra 2d6 fire + restrain on hit (1/SR)",
                    "Frost Rune: +2 to STR/CON ability checks, bonus action for ally +2 (1/SR)",
                    "Stone Rune: charm a creature within 30ft (reaction, 1/SR)",
                    "Hill Rune: resistance to bludgeoning/slashing/piercing (bonus action, 1/SR)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 67, Speed 30ft.\n"
                    "STR 18(+4) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +7, CON +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+4 x2), two handaxes (1d6+4)."
                ),
            },
            8: {
                "class_string": "Fighter (Rune Knight) 8",
                "features": [
                    "ASI: +2 STR (STR becomes 20, +5 modifier)",
                ],
                "notes": "STR increases to 20 (+5). Melee attacks become +8 to hit, Maul 2d6+5, handaxes 1d6+5.",
                "stats": (
                    "AC 16 (chain mail), HP 76, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +8, CON +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x2), two handaxes (1d6+5)."
                ),
            },
            9: {
                "class_string": "Fighter (Rune Knight) 9",
                "features": [
                    "Indomitable (1/LR reroll a failed saving throw)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 85, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +9, CON +7. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x2), two handaxes (1d6+5)."
                ),
            },
            10: {
                "class_string": "Fighter (Rune Knight) 10",
                "features": [
                    "Great Stature (Giant's Might extra damage increases to 1d8, grow 3d4 inches permanently)",
                ],
                "notes": "4 runes known.",
                "stats": (
                    "AC 16 (chain mail), HP 94, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +9, CON +7. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x2), two handaxes (1d6+5)."
                ),
            },
            11: {
                "class_string": "Fighter (Rune Knight) 11",
                "features": [
                    "Extra Attack improvement (3 attacks per Attack action)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 103, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +9, CON +7. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            12: {
                "class_string": "Fighter (Rune Knight) 12",
                "features": [
                    "ASI: Feat (Sentinel — opportunity attacks reduce speed to 0, attack when ally is attacked within 5ft)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 112, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +9, CON +7. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            13: {
                "class_string": "Fighter (Rune Knight) 13",
                "features": [
                    "Indomitable improvement (2/LR reroll failed saving throws)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 121, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 16(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +10, CON +8. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            14: {
                "class_string": "Fighter (Rune Knight) 14",
                "features": [
                    "ASI: Feat (Crusher — on bludgeoning hit push creature 5ft, on crit all attacks vs target have advantage until next turn, +1 CON)",
                ],
                "notes": "CON increases to 17 (still +3 modifier). Crusher synergizes perfectly with maul combat.",
                "stats": (
                    "AC 16 (chain mail), HP 130, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 17(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +10, CON +8. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            15: {
                "class_string": "Fighter (Rune Knight) 15",
                "features": [
                    "Master of Runes (invoke each rune 2/SR instead of 1/SR)",
                ],
                "notes": "5 runes known.",
                "stats": (
                    "AC 16 (chain mail), HP 139, Speed 30ft.\n"
                    "STR 20(+5) DEX 12(+1) CON 17(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +10, CON +8. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            16: {
                "class_string": "Fighter (Rune Knight) 16",
                "features": [
                    "ASI: +2 DEX (DEX becomes 14, +2 modifier)",
                ],
                "notes": "DEX increases to 14 (+2).",
                "stats": (
                    "AC 16 (chain mail), HP 148, Speed 30ft.\n"
                    "STR 20(+5) DEX 14(+2) CON 17(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +10, CON +8. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            17: {
                "class_string": "Fighter (Rune Knight) 17",
                "features": [
                    "Action Surge improvement (2 uses between rests)",
                    "Indomitable improvement (3/LR reroll failed saving throws)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 157, Speed 30ft.\n"
                    "STR 20(+5) DEX 14(+2) CON 17(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +11, CON +9. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            18: {
                "class_string": "Fighter (Rune Knight) 18",
                "features": [
                    "Runic Juggernaut (Giant's Might can increase size to Huge, extra damage increases to 1d10)",
                ],
                "notes": "5 runes known.",
                "stats": (
                    "AC 16 (chain mail), HP 166, Speed 30ft.\n"
                    "STR 20(+5) DEX 14(+2) CON 17(+3) INT 10(+0) WIS 10(+0) CHA 10(+0)\n"
                    "Saves: STR +11, CON +9. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            19: {
                "class_string": "Fighter (Rune Knight) 19",
                "features": [
                    "ASI: Feat (Resilient WIS — +1 WIS, proficiency in WIS saves)",
                ],
                "notes": "WIS increases to 11 (+0). Gains proficiency in WIS saving throws (WIS save becomes +6).",
                "stats": (
                    "AC 16 (chain mail), HP 175, Speed 30ft.\n"
                    "STR 20(+5) DEX 14(+2) CON 17(+3) INT 10(+0) WIS 11(+0) CHA 10(+0)\n"
                    "Saves: STR +11, CON +9, WIS +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x3), two handaxes (1d6+5)."
                ),
            },
            20: {
                "class_string": "Fighter (Rune Knight) 20",
                "features": [
                    "Extra Attack improvement (4 attacks per Attack action)",
                ],
                "stats": (
                    "AC 16 (chain mail), HP 184, Speed 30ft.\n"
                    "STR 20(+5) DEX 14(+2) CON 17(+3) INT 10(+0) WIS 11(+0) CHA 10(+0)\n"
                    "Saves: STR +11, CON +9, WIS +6. Skills: Athletics, Intimidation, Stealth, Survival.\n"
                    "Tools: Dice Set, Thieves' Tools, Smith's Tools.\n"
                    "Weapons: Maul (2d6+5 x4), two handaxes (1d6+5)."
                ),
            },
        },
    },
    "Professor Thaddeus Mercer": {
        "hit_die": 6,
        "con_mod": 1,
        "hp_per_level": 5,  # (6/2 + 1) + 1
        "base_hp": 7,
        "levels": {
            1: {
                "class_string": "Wizard (Order of Scribes) 1",
                "features": [
                    "Arcane Recovery (recover spell slots on short rest)",
                ],
                "cantrips": ["Fire Bolt", "Mage Hand", "Prestidigitation", "Message"],
                "spells": [
                    "Comprehend Languages", "Detect Magic", "Identify",
                    "Mage Armor", "Magic Missile", "Shield",
                ],
                "spell_slots": "2 first-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 7, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 16(+3) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +5, WIS +3. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            2: {
                "class_string": "Wizard (Order of Scribes) 2",
                "features": [
                    "Order of Scribes: Wizardly Quill (conjure magic quill, instant transcription)",
                    "Order of Scribes: Awakened Spellbook (swap damage types, cast rituals faster)",
                ],
                "cantrips": [],
                "spells": ["Thunderwave", "Feather Fall"],
                "spell_slots": "3 first-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 12, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 16(+3) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +5, WIS +3. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            3: {
                "class_string": "Wizard (Order of Scribes) 3",
                "features": [],
                "cantrips": [],
                "spells": ["Misty Step", "Web", "Shatter", "Hold Person"],
                "spell_slots": "4 first-level, 2 second-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 17, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 16(+3) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +5, WIS +3. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            4: {
                "class_string": "Wizard (Order of Scribes) 4",
                "features": [
                    "ASI: +2 INT (INT becomes 18, +4 modifier)",
                ],
                "cantrips": ["Minor Illusion"],
                "spells": ["Counterspell", "Fireball"],
                "spell_slots": "4 first-level, 3 second-level slots",
                "notes": "INT increases to 18 (+4). Spell save DC becomes 14. Spell attack becomes +6.",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 22, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 18(+4) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +6, WIS +3. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            5: {
                "class_string": "Wizard (Order of Scribes) 5",
                "features": [],
                "cantrips": [],
                "spells": ["Hypnotic Pattern", "Dispel Magic"],
                "spell_slots": "4 first-level, 3 second-level, 2 third-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 27, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 18(+4) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +7, WIS +4. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            6: {
                "class_string": "Wizard (Order of Scribes) 6",
                "features": [
                    "Manifest Mind (conjure spectral mind from spellbook, cast spells from its space, prof uses/LR)",
                ],
                "cantrips": [],
                "spells": ["Fly", "Slow"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 32, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 18(+4) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +7, WIS +4. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            7: {
                "class_string": "Wizard (Order of Scribes) 7",
                "features": [],
                "cantrips": [],
                "spells": ["Polymorph", "Banishment"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 1 fourth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 37, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 18(+4) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +7, WIS +4. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            8: {
                "class_string": "Wizard (Order of Scribes) 8",
                "features": [
                    "ASI: +2 INT (INT becomes 20, +5 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 2 fourth-level slots",
                "notes": "INT increases to 20 (+5). Spell save DC becomes 16. Spell attack becomes +8.",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 42, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +8, WIS +4. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            9: {
                "class_string": "Wizard (Order of Scribes) 9",
                "features": [],
                "cantrips": [],
                "spells": ["Wall of Force", "Animate Objects"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 1 fifth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 47, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +9, WIS +5. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            10: {
                "class_string": "Wizard (Order of Scribes) 10",
                "features": [
                    "Master Scrivener (create scroll of 1st or 2nd-level spell for free 1/LR, costs no material components)",
                ],
                "cantrips": [],
                "spells": ["Telekinesis", "Scrying"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 52, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +9, WIS +5. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            11: {
                "class_string": "Wizard (Order of Scribes) 11",
                "features": [],
                "cantrips": [],
                "spells": ["Globe of Invulnerability", "Chain Lightning"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 57, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +9, WIS +5. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            12: {
                "class_string": "Wizard (Order of Scribes) 12",
                "features": [
                    "ASI: Feat (War Caster — advantage on CON saves for concentration, somatic with hands full, opportunity attack cantrip)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 62, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +9, WIS +5. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            13: {
                "class_string": "Wizard (Order of Scribes) 13",
                "features": [],
                "cantrips": [],
                "spells": ["Forcecage", "Teleport"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level, 1 seventh-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 67, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +10, WIS +6. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            14: {
                "class_string": "Wizard (Order of Scribes) 14",
                "features": [
                    "One with the Word (advantage on Arcana checks, if reduced to 0 HP can sacrifice spell levels to stay at 1 HP)",
                ],
                "cantrips": [],
                "spells": ["Simulacrum"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level, 1 seventh-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 72, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +10, WIS +6. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            15: {
                "class_string": "Wizard (Order of Scribes) 15",
                "features": [],
                "cantrips": [],
                "spells": ["Maze", "Feeblemind"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level, 1 seventh-level, 1 eighth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 77, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 12(+1)\n"
                    "Saves: INT +10, WIS +6. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            16: {
                "class_string": "Wizard (Order of Scribes) 16",
                "features": [
                    "ASI: +2 CHA (CHA becomes 14, +2 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level, 1 seventh-level, 1 eighth-level slots",
                "notes": "CHA increases to 14 (+2).",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 82, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 14(+2)\n"
                    "Saves: INT +10, WIS +6. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            17: {
                "class_string": "Wizard (Order of Scribes) 17",
                "features": [],
                "cantrips": [],
                "spells": ["Wish", "Foresight"],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 2 fifth-level, 1 sixth-level, 1 seventh-level, 1 eighth-level, 1 ninth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 87, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 14(+2)\n"
                    "Saves: INT +11, WIS +7. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            18: {
                "class_string": "Wizard (Order of Scribes) 18",
                "features": [
                    "Spell Mastery (choose one 1st-level and one 2nd-level spell to cast at will without expending slots)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 3 fifth-level, 1 sixth-level, 1 seventh-level, 1 eighth-level, 1 ninth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 92, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 14(+2)\n"
                    "Saves: INT +11, WIS +7. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            19: {
                "class_string": "Wizard (Order of Scribes) 19",
                "features": [
                    "ASI: +2 CHA (CHA becomes 16, +3 modifier)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 3 fifth-level, 2 sixth-level, 1 seventh-level, 1 eighth-level, 1 ninth-level slots",
                "notes": "CHA increases to 16 (+3).",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 97, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 16(+3)\n"
                    "Saves: INT +11, WIS +7. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
            20: {
                "class_string": "Wizard (Order of Scribes) 20",
                "features": [
                    "Signature Spells (choose two 3rd-level spells to cast 1/SR without expending slots)",
                ],
                "cantrips": [],
                "spells": [],
                "spell_slots": "4 first-level, 3 second-level, 3 third-level, 3 fourth-level, 3 fifth-level, 2 sixth-level, 2 seventh-level, 1 eighth-level, 1 ninth-level slots",
                "stats": (
                    "AC 12 (15 with Mage Armor), HP 102, Speed 30ft.\n"
                    "STR 8(-1) DEX 14(+2) CON 12(+1) INT 20(+5) WIS 13(+1) CHA 16(+3)\n"
                    "Saves: INT +11, WIS +7. Skills: Arcana, History, Investigation, Perception.\n"
                    "Languages: Common, Elvish, Draconic, Giant, Dwarvish."
                ),
            },
        },
    },
}


def level_up_party(state: dict) -> dict:
    """Level up all party members by one level.

    Updates campaign_state.json party entries with:
      - New level number
      - New class string (e.g., "Artificer (Alchemist) 2")
      - Updated HP
      - New features, spells, and stat changes

    Returns a summary dict describing what changed for logging.
    """
    summary = {}

    for pc_name, class_data in CLASS_DATA.items():
        pc = state.get("party", {}).get(pc_name)
        if not pc:
            continue

        current_level = pc.get("level", 1)
        new_level = current_level + 1

        level_info = class_data["levels"].get(new_level)
        if not level_info:
            summary[pc_name] = f"No level {new_level} data available — skipped."
            continue

        # Update level
        pc["level"] = new_level

        # Update class string
        pc["class"] = level_info["class_string"]

        # Update HP (use pre-calculated total from stats string, or calculate)
        new_hp = class_data["base_hp"] + (class_data["hp_per_level"] * (new_level - 1))
        pc["hp"] = f"{new_hp}/{new_hp}"

        # Store the full stat block for dynamic agent creation
        pc["stat_block"] = level_info["stats"]

        # Store current features for reference
        all_features = []
        for lvl in range(1, new_level + 1):
            lvl_info = class_data["levels"].get(lvl, {})
            all_features.extend(lvl_info.get("features", []))
        pc["features"] = all_features

        # Store current spells for reference (casters only)
        if "spells" in level_info:
            all_spells = []
            all_cantrips = []
            for lvl in range(1, new_level + 1):
                lvl_info = class_data["levels"].get(lvl, {})
                all_spells.extend(lvl_info.get("spells", []))
                all_cantrips.extend(lvl_info.get("cantrips", []))
            pc["known_spells"] = list(dict.fromkeys(all_spells))  # dedupe, preserve order
            pc["cantrips"] = list(dict.fromkeys(all_cantrips))

        if "spell_slots" in level_info:
            pc["spell_slots"] = level_info["spell_slots"]

        # Build summary
        new_features = level_info.get("features", [])
        new_spells = level_info.get("spells", [])
        notes = level_info.get("notes", "")
        parts = [f"Level {current_level} → {new_level}"]
        parts.append(f"HP: {new_hp}")
        if new_features:
            parts.append(f"New features: {', '.join(new_features)}")
        if new_spells:
            parts.append(f"New spells: {', '.join(new_spells)}")
        if notes:
            parts.append(f"Note: {notes}")
        summary[pc_name] = " | ".join(parts)

    return summary


def get_stat_block(pc_name: str, level: int) -> str:
    """Get the full stat block string for a PC at a given level.

    Used by agents.py to dynamically build PC backstories with current stats.
    Returns empty string if no data found.
    """
    class_data = CLASS_DATA.get(pc_name)
    if not class_data:
        return ""
    level_info = class_data["levels"].get(level)
    if not level_info:
        return ""
    return level_info.get("stats", "")


def get_features_summary(pc_name: str, level: int) -> str:
    """Get a formatted summary of all features a PC has at a given level.

    Accumulates features from level 1 through the specified level.
    """
    class_data = CLASS_DATA.get(pc_name)
    if not class_data:
        return ""

    lines = []
    for lvl in range(1, level + 1):
        level_info = class_data["levels"].get(lvl, {})
        features = level_info.get("features", [])
        for feat in features:
            lines.append(f"- {feat}")

    return "\n".join(lines) if lines else "No special features yet."


def get_spells_summary(pc_name: str, level: int) -> str:
    """Get a formatted summary of all spells/cantrips a PC knows at a given level."""
    class_data = CLASS_DATA.get(pc_name)
    if not class_data:
        return ""

    cantrips = []
    spells = []
    slots = ""
    for lvl in range(1, level + 1):
        level_info = class_data["levels"].get(lvl, {})
        cantrips.extend(level_info.get("cantrips", []))
        spells.extend(level_info.get("spells", []))
        if "spell_slots" in level_info:
            slots = level_info["spell_slots"]

    # Dedupe
    cantrips = list(dict.fromkeys(cantrips))
    spells = list(dict.fromkeys(spells))

    parts = []
    if cantrips:
        parts.append(f"Cantrips: {', '.join(cantrips)}")
    if spells:
        parts.append(f"Spells: {', '.join(spells)}")
    if slots:
        parts.append(f"Slots: {slots}")
    return "\n".join(parts) if parts else ""
