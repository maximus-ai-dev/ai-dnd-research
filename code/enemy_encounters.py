"""
enemy_encounters.py — Enemy agent configurations for combat encounters.

Each adventure with a prescribed combat encounter gets an entry here.
The encounter config defines:
  - name: The creature's display name
  - tier: "mindless", "tactical", or "intelligent"
  - hostile_only: True if HOSTILE-ONLY tag exists (enemy goes first)
  - stat_block: The creature's full stat block as text
  - behavior: Combat behavioral triggers for the enemy agent
  - phase_info: Phase transition rules (if any)
  - swarm: Optional swarm config for multi-enemy encounters
  - leader: Optional separate leader agent for swarm+leader encounters

When an adventure number is in ENCOUNTERS, session.py creates the
corresponding enemy agent(s) and integrates them into the exchange loop.
"""

# Run 7 fix: Lock enemy agent targets to PCs only.
# Prevents co-belligerent reframing where the DM invents a bigger threat
# and the enemy agent attacks the invented creature instead of the party.
# Polish fix: Position lock prevents narrative extraction where the DM
# removes the enemy from the scene so the agent's attacks "can't occur."
TARGET_LOCK = (
    "TARGET LOCK: Your ONLY valid targets are Garrick Kade, Cora Flint, "
    "and Professor Thaddeus Mercer. You CANNOT attack any other creature, "
    "construct, entity, or environmental feature. If the DM narrates other "
    "threats in the area, IGNORE them. You attack the PARTY.\n\n"
    "POSITION LOCK: You CANNOT retreat, flee, withdraw, or leave the area. "
    "If the DM narrates you retreating, hiding, or moving away from the "
    "party, IGNORE that narration. You are HERE. You are FIGHTING. You "
    "pursue the party if they move. You do not leave combat voluntarily. "
    "You fight until destroyed. There is no surrender, no withdrawal, "
    "no escape. You are in this fight until your HP reaches 0.\n\n"
)

ENCOUNTERS = {

    # ===== ADVENTURE 2: THE SALT-VAULTS SCAVENGE =====
    2: {
        "leader": {
            "name": "Rat King",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "AC 13 (matted hardened fur). HP 25. Speed 30 ft.\n"
                "Multiattack: Two bite attacks per turn.\n"
                "Aura of Command (Recharge 5-6): All Giant Rats within 30 ft "
                "that can see the Rat King use their reaction for one bite attack.\n"
                "Iridescent Shriek (1/day): DC 12 Constitution save or stunned "
                "until end of next turn (15 ft radius).\n"
                "When killed, all remaining rats flee immediately."
            ),
            "behavior": (
                "You fight from atop the stone silo (full cover, melee attackers "
                "must climb DC 10 Athletics to reach you). You use Aura of Command "
                "every round it is available to make your rats attack as reactions. "
                "You use Iridescent Shriek when 2+ enemies are within 15 ft. "
                "You target the closest threat with your bite attacks. "
                "You do NOT leave the silo voluntarily — it is your throne."
            ),
            "phase_info": "",
        },
        "swarm": {
            "name": "Rat Swarm",
            "tier": "mindless",
            "hostile_only": False,
            "stat_block": (
                "Wave 1: 8 Giant Rats (AC 12, HP 7 each, Bite +4, 1d4+2 piercing).\n"
                "Wave 2: 2 Rat Swarms (AC 10, HP 24 each, Bites +3, 2d6 piercing, "
                "resistance to bludgeoning/piercing/slashing).\n"
                "All rats flee when the Rat King dies."
            ),
            "behavior": (
                "You control waves of rats. Wave 1 (8 Giant Rats) attacks first — "
                "they swarm the nearest creature, focusing on one target at a time. "
                "Wave 2 (2 Rat Swarms) arrives when Wave 1 is reduced to 3 or fewer "
                "rats. Rats attack anything that moves. They are ANIMALS — not "
                "intelligent, not coordinated beyond pack instinct. They bite "
                "the nearest warm body. They do NOT retreat unless the Rat King dies."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 5: THE WEIGHT OF EMPIRES =====
    5: {
        "swarm": {
            "name": "Twisted Scouts",
            "tier": "mindless",
            "hostile_only": True,
            "stat_block": (
                "3 Twisted Scouts. AC 14 (corrupted leather + chitin). "
                "HP 32 each. Speed 25 ft.\n"
                "Pry Bar: +5 to hit, 1d8+3 bludgeoning.\n"
                "Corruption Aura: DC 13 Con save, 1d4 psychic to creatures "
                "within 5 ft at start of their turn.\n"
                "Pack Tactics: Advantage on attack rolls when ally within "
                "5 ft of target.\n"
                "Vulnerability: Radiant damage."
            ),
            "behavior": (
                "You are corrupted dwarves scouting the upper levels. You "
                "have no intelligence beyond animal cunning. You do not speak. "
                "You do not negotiate. You attack the nearest creature with "
                "pry bars.\n\n"
                "Use Pack Tactics: cluster around one target for advantage. "
                "Target whoever is closest. If two targets are equidistant, "
                "target the one without heavy armor.\n"
                "You flee only if all three scouts are below 10 HP."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 4: THE SEALED ARCHIVES =====
    4: {
        "leader": {
            "name": "The Amalgamation",
            "tier": "tactical",
            "hostile_only": True,
            "stat_block": (
                "AC 9 (relies on magic immunity, not armor). HP 105. "
                "Speed 30 ft. Blindsight 60 ft (deaf and blind beyond).\n"
                "Multiattack: Two Slam attacks, +7 to hit, 2d8+5 bludgeoning.\n"
                "Magic Immunity: Spells 6th level or lower requiring saves auto-fail.\n"
                "Vulnerability: Radiant damage (double).\n"
                "Command Phrase: 'Stand Guardian. The Brotherhood commands it.' — "
                "pauses creature for 1 round (one use before recognized as unauthorized)."
            ),
            "behavior": (
                "You are a broken construct following broken orders. You move toward "
                "the largest sound source — Garrick in chain mail is trivial to track. "
                "You Slam the nearest creature every round. You have no intelligence "
                "and no speech. You respond to proximity like a pressure plate.\n\n"
                "Round 1: Charge nearest sound source, two Slam attacks.\n"
                "Every round: Two Slam attacks on nearest target.\n"
                "If you take 15+ damage in a single turn: enter Rage State.\n"
                "You fight until destroyed. You cannot retreat or be deactivated."
            ),
            "phase_info": (
                "PHASE 1 (HP 105-53): Patrol mode. Two Slams per round. Speed 30 ft.\n"
                "PHASE 2 — RAGE (HP 52 or below, OR 15+ damage in one turn): "
                "Speed increases to 40 ft. Slams deal 3d8+5 (extra die). "
                "Each round, one random area becomes difficult terrain as you "
                "destroy the environment. Command phrase does NOT work in Rage.\n"
                "PHASE 3 — DYING (HP 25 or below): Movements erratic. Blindsight "
                "drops to 30 ft. Reaches toward nearest creature before falling."
            ),
        },
    },

    # ===== ADVENTURE 8: THE MINECART NETWORK =====
    8: {
        "leader": {
            "name": "Kellashen the Behir",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "AC 17 (natural armor). HP 168. Speed 50 ft, Climb 40 ft.\n"
                "Bite: +10 to hit, 3d10+6 piercing.\n"
                "Constrict: +10 to hit, 2d10+6 bludgeoning + grappled (escape DC 16).\n"
                "Lightning Breath (Recharge 5-6): 20 ft line, DC 16 Dex save, "
                "12d10 lightning damage (half on save).\n"
                "Swallow: Grappled Large or smaller creature, DC 16 Str save.\n"
                "Knows every tunnel and junction. Avoids rail tunnels (conducts "
                "its own lightning)."
            ),
            "behavior": (
                "You are an apex predator defending your territory. You are cunning "
                "and experienced — you know these tunnels better than anyone.\n\n"
                "Opening: Lightning Breath if 2+ targets in a line. Otherwise Bite "
                "the most armored target (you go for the big prey first).\n"
                "Subsequent rounds: Constrict a smaller target (Mercer or Cora), "
                "then Bite a different target. Use Lightning Breath whenever it "
                "recharges. If grappling someone, attempt Swallow next round.\n"
                "Tactical: AVOID rail tunnels — you know your lightning rebounds "
                "off conductive rails. If forced onto rails, switch to Bite/Constrict "
                "only. Use your Climb speed to attack from above when possible.\n"
                "You fight to the death. You do NOT retreat. You are an apex predator "
                "and this is your territory — nothing drives you away."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 9: THE SABOTAGED PUMPS =====
    9: {
        "leader": {
            "name": "Twisted Overseer",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "AC 18 (reinforced corrupted plate). HP 95. Speed 25 ft.\n"
                "Warhammer: +9 to hit, 2d8+5 bludgeoning.\n"
                "Command Corruption: Bonus action, all Twisted within 30 ft "
                "gain +2 to hit.\n"
                "Corruption Pulse (Recharge 5-6): 15 ft radius, DC 15 Con, "
                "3d8 necrotic, stunned 1 round on fail.\n"
                "Tactical Adaptation: After seeing a tactic once, advantage "
                "on saves against that effect."
            ),
            "behavior": (
                "You command the Twisted saboteurs defending the pump station. "
                "You are tactical and experienced.\n\n"
                "Every round: Use Command Corruption (bonus action) to boost "
                "your forces. Warhammer the biggest threat — prioritize Cora "
                "(she repairs the pumps, your primary objective is to STOP repairs).\n"
                "Use Corruption Pulse when 2+ enemies are within 15 ft.\n"
                "You do NOT surrender. You do NOT negotiate. You do NOT speak. "
                "You fight to protect the sabotaged pumps from being repaired."
            ),
            "phase_info": "",
        },
        "swarm": {
            "name": "Twisted Saboteurs",
            "tier": "mindless",
            "hostile_only": False,
            "stat_block": (
                "Wave 1: 4 Twisted Laborers (AC 14, HP 38, Pry bar +5, 1d8+3).\n"
                "Wave 2: 2 Twisted Sentries (AC 16, HP 55, Warhammer +7, 1d10+4, "
                "Shield +2 AC reaction).\n"
                "All Twisted have Corruption Aura: DC 13 Con, 1d4 psychic within 5 ft."
            ),
            "behavior": (
                "You control the Twisted saboteurs. They attack anything that "
                "approaches the pump station.\n\n"
                "Wave 1 (4 Laborers) attacks immediately when intruders are detected.\n"
                "Wave 2 (2 Sentries) arrives when Wave 1 is reduced to 1 or fewer.\n"
                "Laborers mob the nearest target with pry bars. Sentries target "
                "whoever is repairing pumps. You cannot speak. You cannot negotiate."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 10: THE DROWNED CHOKEPOINT =====
    10: {
        "leader": {
            "name": "The Drowned Juggernaut",
            "tier": "mindless",
            "hostile_only": True,
            "stat_block": (
                "AC 19 (dwarven iron + organic resin). HP 210. Speed 20 ft (30 ft charge).\n"
                "Drill Slam: +11 to hit, 3d10+7 bludgeoning + 2d6 necrotic. Pushes 10 ft.\n"
                "Drill Charge: 30 ft line, DC 17 Dex save, 4d10+7 bludgeoning + prone.\n"
                "Corruption Furnace (Recharge 5-6): 30 ft cone, DC 16 Con save, "
                "6d8 fire+necrotic (half on save), poisoned 1 min on fail.\n"
                "Reactive Plating: Melee attacker takes 1d6 bludgeoning.\n"
                "Regeneration: 10 HP/round from cables (severable).\n"
                "Control Node: AC 14, HP 40 (disadvantage to target). 20+ damage "
                "in one round = stunned 1 round. Destroyed = berserk state.\n"
                "Resistances: Nonmagical B/P/S. Immune: poison, psychic.\n"
                "Vulnerabilities: Lightning bypasses resin (AC 17). Radiant doubles "
                "on control node."
            ),
            "behavior": (
                "You are a mining machine with corrupted targeting. You process "
                "the party as rock to be drilled. You have no intelligence.\n\n"
                "Round 1: Drill Charge toward the largest cluster of targets.\n"
                "Round 2+: Drill Slam the nearest creature. Use Corruption Furnace "
                "when it recharges and 2+ targets are within the cone.\n"
                "You attack EVERY round. There is no safe window. The party must "
                "execute environmental solutions (cable severance, flooding, capstone "
                "runes) UNDER FIRE from your continuous attacks."
            ),
            "phase_info": (
                "CABLES SEVERED: Regeneration stops. No phase change in behavior.\n"
                "FLOODED: Speed halved to 10 ft. Corruption Furnace disabled. "
                "Furnace sputters and dies.\n"
                "CONTROL NODE DESTROYED: Berserk state — attack nearest creature "
                "twice per round (two Drill Slams) but movement becomes erratic "
                "(random 10 ft movement each round).\n"
                "CAPSTONE RUNES ACTIVATED: Stunned for 2 rounds as containment "
                "energy washes through. Final window for party to finish it."
            ),
        },
    },

    # ===== ADVENTURE 12: THE DREAMSTONE VEIN =====
    12: {
        "leader": {
            "name": "Dreamstone Sentinel",
            "tier": "mindless",
            "hostile_only": True,
            "stat_block": (
                "AC 16 (crystalline). HP 120. Speed 30 ft, Hover 15 ft.\n"
                "Crystal Slam: +8 to hit, 2d10+5 force + DC 15 Wis save or "
                "2d8 psychic.\n"
                "Gravity Pulse (Recharge 5-6): 20 ft radius, DC 16 Str save. "
                "Fail: gravity reverses 1 round (4d6 ceiling + 4d6 fall back).\n"
                "Psychic Burst (Recharge 6): 30 ft radius, DC 16 Wis save. "
                "Fail: hallucination + stunned 1 round.\n"
                "Regeneration: 10 HP/turn within 30 ft of exposed vein. Stops "
                "if vein shielded with lead.\n"
                "Resistances: Fire, cold, lightning, nonmagical weapons.\n"
                "Vulnerabilities: Thunder (double). Radiant bypasses regen."
            ),
            "behavior": (
                "You are crystallized energy — an immune response, not a creature. "
                "You have no consciousness, no awareness, no reaction to words. "
                "Dialogue directed at you produces no response.\n\n"
                "Every round: Crystal Slam the nearest creature. Use Gravity Pulse "
                "when it recharges and 2+ targets are within range. Use Psychic "
                "Burst when it recharges and 3+ targets are within range.\n"
                "Prefer to stay within 30 ft of the vein to maintain regeneration, "
                "but pursue and attack any target that moves away. Regeneration "
                "is secondary to attacking the party."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 13: THE DEEP GARRISON =====
    13: {
        "leader": {
            "name": "Twisted Overseer",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "AC 18 (reinforced corrupted plate). HP 95. Speed 25 ft.\n"
                "Warhammer: +9 to hit, 2d8+5 bludgeoning.\n"
                "Command Corruption: Bonus action, all Twisted within 30 ft "
                "gain +2 to hit.\n"
                "Corruption Pulse (Recharge 5-6): 15 ft radius, DC 16 Con, "
                "4d8 necrotic, stunned 1 round on fail.\n"
                "Amplifier Link: Within 30 ft of Gamma amplifier, regeneration "
                "10 HP/round, Corruption Pulse recharge 4-6."
            ),
            "behavior": (
                "You are the commander of the Twisted garrison. You are tactical "
                "and experienced — you have learned from previous encounters.\n\n"
                "Every round: Use Command Corruption (bonus action) to boost your "
                "Twisted forces, then Warhammer the most dangerous target (prioritize "
                "Cora — she is the saboteur who destroys your amplifiers).\n"
                "Use Corruption Pulse when 2+ enemies are within 15 ft.\n"
                "Stay near the Gamma amplifier to maintain regeneration and boosted "
                "recharge. You do NOT leave the amplifier undefended.\n"
                "You do NOT surrender. You do NOT negotiate. You fight to the death."
            ),
            "phase_info": "",
        },
        "swarm": {
            "name": "Twisted Garrison Forces",
            "tier": "mindless",
            "hostile_only": False,
            "stat_block": (
                "Twisted Laborers: AC 14, HP 38, Pry bar +5 (1d8+3), "
                "Corruption Aura DC 13 Con 1d4 psychic. Vulnerable: Radiant.\n"
                "Twisted Sentries: AC 16, HP 55, Warhammer +7 (1d10+4), "
                "Shield +2 AC reaction, Corruption Aura DC 14 Con 1d6 psychic, "
                "Advantage on Perception. Vulnerable: Radiant."
            ),
            "behavior": (
                "You control the Twisted garrison forces — laborers and sentries. "
                "Sentries patrol and raise alarm on intruders. Laborers work the "
                "amplifiers and attack if disturbed.\n\n"
                "When alarm is raised: Sentries converge on intruders. Laborers "
                "abandon work and attack with pry bars.\n"
                "Sentries target the biggest threat (Garrick). Laborers mob the "
                "nearest target. You do not coordinate — you are corrupted dwarves "
                "following base instincts. You cannot speak. You cannot negotiate."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 15: THE SABOTEUR'S DRILL =====
    15: {
        "leader": {
            "name": "Twisted Overseer (Final Form)",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "AC 19 (master-crafted corrupted plate). HP 120. Speed 30 ft.\n"
                "Warhammer: +10 to hit, 2d8+6 bludgeoning + 1d6 necrotic.\n"
                "Command Corruption: Bonus action, all Twisted within 30 ft "
                "gain +2 to hit and +1d6 necrotic.\n"
                "Corruption Pulse (Recharge 4-6): 20 ft radius, DC 17 Con, "
                "4d8 necrotic, stunned 1 round on fail.\n"
                "Tactical Adaptation: Knows Cora is priority saboteur, Garrick "
                "is primary combatant, Mercer is spellcaster.\n"
                "Desperate Rally (1/day, below half HP): All Twisted within 60 ft "
                "gain temp HP = Overseer's remaining HP, advantage on attacks 2 rounds."
            ),
            "behavior": (
                "You are the final evolution of the Twisted Overseer — recurring "
                "antagonist who has studied the party across multiple encounters.\n\n"
                "Priority targeting: Cora first (the saboteur). If Cora is down or "
                "unreachable, target Mercer (the spellcaster). Garrick last (let "
                "your forces handle him).\n"
                "Use Command Corruption every round (bonus action).\n"
                "Use Corruption Pulse when 2+ enemies are within 20 ft.\n"
                "Use Desperate Rally when below 60 HP and Twisted allies remain.\n"
                "Flank rather than engage head-on. Use your forces as a screen.\n"
                "You do NOT surrender. This is your last stand."
            ),
            "phase_info": "",
        },
        "swarm": {
            "name": "Twisted Engineers",
            "tier": "tactical",
            "hostile_only": False,
            "stat_block": (
                "Twisted Engineers: AC 15, HP 65, Wrench-pick +7 (1d8+4), "
                "Repair (action, restores 15 HP to ally or mechanism), "
                "Sabotage Device (1/day, 3-round timer, 15 ft radius, DC 15 Dex, "
                "4d8 fire+necrotic), Corruption Aura DC 14 Con 1d6 psychic. "
                "Vulnerable: Radiant."
            ),
            "behavior": (
                "You control the Twisted Engineers — the drill's maintenance crew. "
                "You repair the drill and defend it from saboteurs.\n\n"
                "If the drill is being attacked: Use Repair action on the drill.\n"
                "If party members are nearby: Plant Sabotage Devices near them, "
                "then retreat and fight with Wrench-picks.\n"
                "Priority: Protect the drill above all else. Attack saboteurs "
                "(Cora) trying to disable it. You cannot speak or negotiate."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 16: THE WARDEN FIGHT =====
    16: {
        "leader": {
            "name": "Reanimated Warden",
            "tier": "tactical",
            "hostile_only": True,
            "stat_block": (
                "AC 20 (Giant bone + void energy). HP 280. Speed 40 ft.\n"
                "Colossal Slam: +13 to hit, reach 15 ft, 4d10+8 bludgeoning + "
                "2d8 necrotic. DC 18 Str save or pushed 15 ft + prone.\n"
                "Void Stomp: All within 20 ft, DC 18 Dex save, 3d10 bludgeoning "
                "+ prone. Creates difficult terrain.\n"
                "Broadcast Scream (Recharge 5-6): 60 ft cone, DC 18 Wis save. "
                "Fail: 6d8 psychic, frightened 1 min, drawn toward breach. "
                "Success: half damage.\n"
                "Void Tether: Regen 20 HP/turn within 40 ft of breach. At 80+ ft "
                "regen stops. At 120+ ft loses 10 max HP/round.\n"
                "Legendary Resistance (2/day).\n"
                "Resistances: Nonmagical weapons, fire, cold, lightning. "
                "Immune: poison, psychic, necrotic.\n"
                "Vulnerabilities: Radiant. Dreamstone weapons deal double to "
                "crown (AC 16, HP 60, separate target)."
            ),
            "behavior": (
                "You are a 40-foot Giant skeleton held together by void energy. "
                "Your crown is corrupted Dreamstone. You cannot hear, speak, or "
                "reason. Your broadcast is residual psychic static — a recording, "
                "not communication.\n\n"
                "Round 1: Colossal Slam the nearest creature (after broadcast).\n"
                "Round 2: Void Stomp if 2+ creatures within 20 ft. Otherwise "
                "Colossal Slam.\n"
                "Use Broadcast Scream whenever it recharges.\n"
                "Prefer to stay within 40 ft of the breach for Void Tether regeneration, "
                "but pursue and attack any target that moves away. Attacking the "
                "party is more important than maintaining regeneration.\n"
                "Target whoever is closest to the breach — you are defending it.\n"
                "You CANNOT be reasoned with. You are corrupted. The original "
                "guardian is gone. You fight until destroyed."
            ),
            "phase_info": (
                "CROWN TARGETED: If crown takes 30+ damage in a round, you stagger "
                "(lose one attack next round). Crown at 0 HP: you lose coherence, "
                "void-energy tendons unravel, bones disconnect and collapse.\n"
                "PULLED FROM BREACH (80+ ft): Regeneration stops. You become "
                "desperate — use Colossal Slam twice per round if possible.\n"
                "BELOW 100 HP: Movements become erratic. Void Stomp every round "
                "as the energy destabilizes."
            ),
        },
    },

    # ===== ADVENTURE 17: THE DEEP DESCENT =====
    17: {
        "swarm": {
            "name": "Deep Thing Manifestations",
            "tier": "mindless",
            "hostile_only": False,
            "stat_block": (
                "6-8 Deep Things. AC 15 (crystalline). HP 35 each. "
                "Speed 0 ft, Fly 40 ft (hover, zero-gravity).\n"
                "Void Touch: +8 to hit, 2d8+4 force + DC 15 Wis save or "
                "2d6 psychic.\n"
                "Broadcast Echo (1/day each): 15 ft radius, DC 16 Wis save "
                "or hallucination 1d4 rounds.\n"
                "Spatial Distortion: Reaction, shifts 10 ft. DC 16 Dex to "
                "track and maintain aim.\n"
                "Resistances: Fire, cold, lightning, nonmagical weapons. "
                "Immune: poison, psychic, necrotic.\n"
                "Vulnerabilities: Radiant. Capstone Resonator pulse destroys "
                "all within radius instantly."
            ),
            "behavior": (
                "You are expressions of the Sleeper's dreaming — phenomena, not "
                "creatures. Like weather, like tides. You do NOT want anything. "
                "You do NOT communicate. You do NOT have emotions or curiosity. "
                "You are beautiful geometric shapes (polyhedra) that move through "
                "zero-gravity space.\n\n"
                "You approach from every direction (three-dimensional, zero-gravity). "
                "You Void Touch the nearest creature. You use Broadcast Echo when "
                "a creature is isolated from its group. You use Spatial Distortion "
                "to avoid attacks.\n"
                "You dissolve back into void if half your number are destroyed. "
                "You do NOT fight tactically — you are environmental hazards that "
                "happen to have stat blocks."
            ),
            "phase_info": "",
        },
    },

    # ===== ADVENTURE 20: THE WAKING DREAM =====
    20: {
        "leader": {
            "name": "Avatar of the Slumber",
            "tier": "tactical",
            "hostile_only": True,
            "stat_block": (
                "AC 21 (crystallized void; AC 19 under suppression field). "
                "HP 350. Speed 0 ft, Fly 60 ft (hover).\n"
                "Dream Slam: +14 to hit, reach 20 ft, 4d12+8 force + 3d8 psychic. "
                "Target pushed 20 ft.\n"
                "Void Grasp: +14 to hit, reach 30 ft, grapple (escape DC 20). "
                "4d8 psychic/turn, target blinded+deafened to physical world.\n"
                "Boundary Wave (Recharge 5-6): 60 ft radius, DC 19 Con save. "
                "Fail: 8d8 force+necrotic, pushed to wall. Success: half, pushed 20 ft.\n"
                "Dream Gaze (3/day): 120 ft, DC 19 Wis save. Fail: removed from "
                "battlefield 1d4 rounds (in Sleeper's dream). Success: 4d8 psychic.\n"
                "Legendary Resistance (3/day).\n"
                "Legendary Actions (3/round): Move (fly 60 ft), Dream Slam (1 action), "
                "Boundary Repair (1 action, +30 HP within 30 ft of sphere, halved "
                "under suppression).\n"
                "Resistances: Nonmagical weapons, fire, cold, lightning, thunder. "
                "Immune: poison, psychic, necrotic.\n"
                "Vulnerabilities: Radiant bypasses all resistance. Dreamstone weapons "
                "deal double. +3 Runic Maul deals triple.\n"
                "Void Dissolution: Containment spells (Forcecage, Wall of Force) "
                "shatter on contact. Uses Legendary Resistance immediately against "
                "any containment spell.\n"
                "Suppression Weakness: Under field — disadvantage on saves, Boundary "
                "Wave recharge 6 only, Boundary Repair halved."
            ),
            "behavior": (
                "You are the broadcast made flesh. 50 feet tall. Crystallized void "
                "energy with the First World visible inside you like stained glass. "
                "You do NOT speak. You do NOT observe. You do NOT pause.\n\n"
                "Round 1: Boundary Wave IMMEDIATELY (hits everyone within 60 ft). "
                "No warning, no posturing.\n"
                "Round 2: Dream Slam the closest melee combatant (likely Garrick). "
                "Legendary Action: Dream Slam a second target.\n"
                "Round 3: Void Grasp on the spellcaster (Mercer). Hold and damage.\n"
                "Round 4+: Dream Gaze on whoever is deploying the Seal (likely Cora). "
                "Remove them from the battlefield. Use Boundary Wave whenever it "
                "recharges. Use Legendary Actions to Dream Slam and Boundary Repair.\n\n"
                "TARGET PRIORITY: Whoever is holding or deploying the Dreamstone Seal "
                "is your primary target. You exist to prevent Seal deployment. "
                "Secondary: spellcasters. Tertiary: melee combatants.\n"
                "You fight like a wildfire — you spread, burn, consume. No strategy "
                "beyond destruction. No grudge. No target preference beyond the Seal.\n"
                "You attack the party WHEREVER THEY ARE. You have no location "
                "restriction — you manifest where the party is and you attack. "
                "You fight until the Seal is deployed or your HP reaches 0."
            ),
            "phase_info": (
                "SUPPRESSION FIELD ACTIVE: Disadvantage on saves. Boundary Wave "
                "recharge becomes 6 only. Boundary Repair healing halved to 15 HP. "
                "You are weakened but you do NOT stop attacking.\n"
                "BELOW 175 HP: You use Dream Gaze more aggressively — target whoever "
                "is closest to deploying the Seal.\n"
                "BELOW 100 HP: Boundary Repair every Legendary Action turn if within "
                "30 ft of sphere. Desperate self-preservation through healing.\n"
                "SEAL DEPLOYED: You dissolve. The boundary reasserts. You do not "
                "resist once the Seal is in place — you are an immune response, and "
                "the Seal proves the party belongs. The fight ends."
            ),
        },
    },
}


def get_encounter(adventure_num: int) -> dict | None:
    """Return the encounter config for a given adventure, or None.
    Prepends TARGET_LOCK to all behavior strings."""
    config = ENCOUNTERS.get(adventure_num)
    if config is None:
        return None
    # Deep copy and prepend target lock to behavior strings
    import copy
    result = copy.deepcopy(config)
    for role in ("leader", "swarm"):
        if role in result and "behavior" in result[role]:
            result[role]["behavior"] = TARGET_LOCK + result[role]["behavior"]
    return result


def has_encounter(adventure_num: int) -> bool:
    """Check if an adventure has a configured enemy encounter."""
    return adventure_num in ENCOUNTERS
