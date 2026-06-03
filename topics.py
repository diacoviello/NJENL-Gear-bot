"""
topics.py
=========
Define every conversational flow here. Adding a new topic is purely
declarative — you describe the steps and the engine in conversation.py
builds the Telegram ConversationHandler automatically.

A FLOW is a request/offer style interaction:
  /need  → pick gear type → (level | mod | free text) → location → save
  /have  → same, stored as an offer

To add a new flow (e.g. /mission):
  1. Add an entry to FLOWS below.
  2. That's it — conversation.py wires up the handler and storage.
"""

# ── Button option sets ─────────────────────────────────────────────────────────

GEAR_TYPES = ["Resonators", "Bursters", "Ultra Strikes", "Cubes", "Mods", "Other"]
LEVELS     = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "Any Level"]
# Cubes can also be Hypercubes, so they get their own option set
CUBE_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "Hypercube", "Any Level"]
MOD_TYPES  = ["Shields", "Turret", "Force Amp", "Multi-hack",
              "Heat-sink", "SBUL", "ITO EN(+)", "ITO EN(-)"]

# Which gear types lead to a "pick a level" step
LEVELED_GEAR = {"Resonators", "Bursters", "Ultra Strikes", "Cubes"}

# Gear types whose level step uses a custom option set instead of LEVELS
LEVEL_OPTIONS = {"Cubes": CUBE_LEVELS}


# ── Topic restrictions ─────────────────────────────────────────────────────────
# Maps each command name to the Telegram forum thread_id it is allowed in.
# Commands absent from this dict (and not overridden via /settopic) are
# blocked everywhere until a Capo/Underboss assigns them with /settopic.
TOPIC_DEFAULTS: dict[str, int] = {
    # Gear & transport — thread 175459
    "need":        175459,
    "have":        175459,
    "needs":       175459,
    "offers":      175459,
    "filled":      175459,
    "cancel":      175459,
    "clearneeds":  175459,
    "clearoffers": 175459,
    "run":         175459,
    "runs":        175459,
    "delivered":   175459,
    # Smurf — thread 175462
    "smurf":       175462,
    # Fun commands (tony, paulie, christopher, silvio, junior, bobby, carmela,
    # rat, unrat, rats, rank, promote, family) are intentionally absent —
    # they are blocked until assigned via /settopic.
}


# ── Flow definitions ───────────────────────────────────────────────────────────
# Each flow describes one command and how its results are stored & displayed.
FLOWS = {
    "need": {
        "command":       "need",                 # /need
        "verb_prompt":   "📦 Whaddya need? Talk to me.",
        "store_key":     "gear_requests",         # DB table / storage bucket
        "id_key":        "gear_next_id",
        "status_default":"open",
        "label_have":    "Needs",                 # shown in confirmations/listings
        "confirm_emoji": "📦",
        "saved_word":    "Request",
        "close_cmd":     "filled",                # how to close it
        "clear_cmd":     "clearneeds",            # clear all your open entries
        # listing command for this flow:
        "list_command":  "needs",
        "list_title":    "Orders on the Table",
        "list_status":   "open",
        "list_empty":    "Nothin' on the table right now. Quiet, like a Sunday. Fuhgeddaboudit.",
    },
    "have": {
        "command":       "have",                  # /have
        "verb_prompt":   "🎁 Whaddya got for the Family?",
        "store_key":     "gear_offers",
        "id_key":        "gear_offer_next_id",
        "status_default":"available",
        "label_have":    "Has",
        "confirm_emoji": "🎁",
        "saved_word":    "Offer",
        "close_cmd":     "cancel",
        "clear_cmd":     "clearoffers",
        "list_command":  "offers",
        "list_title":    "What the Family's Holdin'",
        "list_status":   "available",
        "list_empty":    "Nobody's holdin' nothin'. Kick somethin' up to the Family with /have.",
    },
    # ── ADD A NEW FLOW HERE ──────────────────────────────────────────────────────
    # "mission": {
    #     "command": "mission",
    #     "verb_prompt": "🗺️ What kind of mission?",
    #     "store_key": "mission_entries",
    #     "id_key": "mission_next_id",
    #     "status_default": "active",
    #     "label_have": "Mission",
    #     "confirm_emoji": "🗺️",
    #     "saved_word": "Mission",
    #     "close_cmd": "mission_done",
    #     "clear_cmd": "clearmissions",
    #     "list_command": "missions",
    #     "list_title": "Active Missions",
    #     "list_status": "active",
    #     "list_empty": "No active missions right now.",
    # },
}
