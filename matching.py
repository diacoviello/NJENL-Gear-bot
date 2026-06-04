"""
matching.py
===========
After a gear entry is saved, scan the opposite bucket for compatible entries
and DM those users to let them know.

  New offer saved  → check open needs   → DM the needers
  New need saved   → check open offers  → DM the offerers

Matching logic:
  - Same base gear type (Resonators, Bursters, etc.)
  - Compatible level: must be equal OR either side is "Any Level"
  - Location overlap: at least one significant word shared between the two location strings
  - "Other" gear (free-text) is never matched — too ambiguous

DMs are best-effort; if the user hasn't started the bot privately the error
is silently swallowed.
"""

import re

from topics import GEAR_TYPES

_LEVEL_RE   = re.compile(r"\b(L[1-8]|Hypercube|Any Level)\b", re.IGNORECASE)
# Words too generic to constitute a location match
_STOP_WORDS = {"near", "in", "around", "at", "by", "the", "and", "nj", "ny", "ct", "pa", "de"}


# ── Item comparison ───────────────────────────────────────────────────────────────

def _gear_type(items: str) -> str | None:
    items_lower = items.lower()
    for gear in GEAR_TYPES:
        if gear.lower() in items_lower:
            return gear
    return None


def _level(items: str) -> str | None:
    m = _LEVEL_RE.search(items)
    return m.group(1).upper() if m else None


def _items_match(a: str, b: str) -> bool:
    gear_a, gear_b = _gear_type(a), _gear_type(b)
    if not gear_a or not gear_b or gear_a != gear_b:
        return False
    if gear_a == "Other":
        return False  # free-text gear; too risky to match
    level_a, level_b = _level(a), _level(b)
    if level_a and level_b:
        return level_a == level_b or "ANY LEVEL" in (level_a, level_b)
    return True  # no levels present; gear-type match is enough


# ── Location comparison ───────────────────────────────────────────────────────────

def _location_match(loc_a: str, loc_b: str) -> bool:
    sig = lambda loc: {
        w.lower() for w in re.split(r"[\s,]+", loc)
        if len(w) > 3 and w.lower() not in _STOP_WORDS
    }
    return bool(sig(loc_a) & sig(loc_b))


# ── Public API ────────────────────────────────────────────────────────────────────

async def notify_matches(bot, storage, flow_key: str, new_entry: dict):
    """Check the opposite bucket for entries compatible with new_entry and DM
    their owners.  Silently skips DMs that fail (user never started the bot)."""
    if flow_key == "have":
        counterpart_store  = "gear_requests"
        counterpart_status = "open"
        def build_msg(match_entry):
            return (
                f"🔔 *Heads up* — someone just posted an offer that might cover your need!\n\n"
                f"📦 *Offer:* {new_entry['items']}  by {new_entry['username']}"
                f"  near _{new_entry['location']}_\n"
                f"📋 *Your need:* #{match_entry['id']} — {match_entry['items']}"
                f"  near _{match_entry['location']}_\n\n"
                f"Check `/offers` and reach out to 'em."
            )
    else:
        counterpart_store  = "gear_offers"
        counterpart_status = "available"
        def build_msg(match_entry):
            return (
                f"🔔 *Heads up* — someone just posted a need that matches what you've got!\n\n"
                f"📦 *Need:* {new_entry['items']}  by {new_entry['username']}"
                f"  near _{new_entry['location']}_\n"
                f"📋 *Your offer:* #{match_entry['id']} — {match_entry['items']}"
                f"  near _{match_entry['location']}_\n\n"
                f"Check `/needs` and reach out to 'em."
            )

    candidates = [
        e for e in storage.list(counterpart_store)
        if e["status"] == counterpart_status
        and e["user_id"] != new_entry["user_id"]
    ]

    for entry in candidates:
        if not _items_match(new_entry["items"], entry["items"]):
            continue
        if not _location_match(new_entry["location"], entry["location"]):
            continue
        try:
            await bot.send_message(entry["user_id"], build_msg(entry), parse_mode="Markdown")
        except Exception:
            pass
