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


# ── Flow definitions ───────────────────────────────────────────────────────────
# Each flow describes one command and how its results are stored & displayed.
FLOWS = {
    "need": {
        "command":       "need",                 # /need
        "verb_prompt":   "📦 What type of gear do you need?",
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
        "list_title":    "Open Gear Requests",
        "list_status":   "open",
        "list_empty":    "🎉 No open gear requests right now!",
    },
    "have": {
        "command":       "have",                  # /have
        "verb_prompt":   "🎁 What type of gear do you have?",
        "store_key":     "gear_offers",
        "id_key":        "gear_offer_next_id",
        "status_default":"available",
        "label_have":    "Has",
        "confirm_emoji": "🎁",
        "saved_word":    "Offer",
        "close_cmd":     "cancel",
        "clear_cmd":     "clearoffers",
        "list_command":  "offers",
        "list_title":    "Available Gear Offers",
        "list_status":   "available",
        "list_empty":    "No gear offers posted yet. Use /have to offer some!",
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
