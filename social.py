"""
social.py
=========
Two social features for group chats.

Rat system — track snitches per-chat:
  /rat @username   — mark someone as a rat
  /unrat @username — exonerate them
  /rats            — list current rats

Rank system — hierarchy tied to actual Telegram group roles:
  Underboss  = group owner (creator)
  Capo       = group admin (administrator)
  Soldier    = regular member promoted by a Capo or Underboss
  Associate  = everyone else

  /rank            — show your own rank
  /promote         — reply to a message to promote that user to Soldier (Capo/Underboss only)
  /family          — show the full roster: Underboss, Capos, Soldiers
"""

import random
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from topic_guard import topic_allowed

# ── Flavor text ─────────────────────────────────────────────────────────────────

_RAT_PHRASES = [
    "Word on the street is {username} been singin' to the feds.",
    "{username} ain't to be trusted. I got it on good authority.",
    "You wanna know who the rat is? Look at {username}.",
    "I heard {username} been talking. The wrong kind of talking.",
    "{username}'s been running their mouth to people they shouldn't. I'm just sayin'.",
    "That's it — {username} is a rat. I'm calling it right now.",
    "You know what they say about {username}? They say too much.",
    "Don't turn your back on {username}. I'm putting it on record.",
]

_UNRAT_PHRASES = [
    "{username} is off the hook. Consider 'em clean.",
    "I looked into it. {username} ain't a rat. My mistake.",
    "Turns out {username} was straight the whole time. Show some respect.",
    "{username} is exonerated. We don't speak of this again. Capisce?",
    "I was wrong about {username}. That don't happen often. Don't make a thing of it.",
]

_RANK_FLAVOR = {
    "Underboss": "You're running this thing. The boss of bosses. Don't mess it up.",
    "Capo":      "You're a captain. People answer to you. Use it wisely.",
    "Soldier":   "You're a made man. Earned your stripes — now act like it.",
    "Associate": "You're with us but not of us. Yet. Keep your head down and do the work.",
}

_RANK_EMOJI = {
    "Underboss": "👑",
    "Capo":      "🎖️",
    "Soldier":   "⚔️",
    "Associate": "🔷",
}


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _uname(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


async def _get_rank(context, chat_id: int, user_id: int, storage) -> str:
    """Return the rank name for a user based on their Telegram role + stored promotions."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = member.status
    except Exception:
        status = "member"

    if status == "creator":
        return "Underboss"
    if status == "administrator":
        return "Capo"

    soldiers = storage.get(f"soldiers:{chat_id}", [])
    if any(s.get("id") == user_id for s in soldiers):
        return "Soldier"
    return "Associate"


def _parse_target(update: Update, context):
    """Return (user_id | None, display_name | None) from a reply or text_mention entity."""
    # Reply-to is the most reliable source of user_id
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        return user.id, _uname(user)

    # text_mention entities also carry the full User object
    for entity in update.message.entities or []:
        if entity.type == "text_mention" and entity.user:
            return entity.user.id, _uname(entity.user)

    # Plain @mention — username only, no user_id
    if context.args:
        username = context.args[0]
        if not username.startswith("@"):
            username = "@" + username
        return None, username

    return None, None


def _group_only(func):
    """Decorator: block these commands in private chats."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                "This is a group thing. Take it to the Family chat."
            )
            return
        await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ── Rat system ───────────────────────────────────────────────────────────────────

@_group_only
async def rat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "rat"):
        return
    _, username = _parse_target(update, context)
    if not username:
        await update.message.reply_text(
            "Who's the rat? Name a name. `/rat @username`", parse_mode="Markdown"
        )
        return

    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id
    rats = storage.get(f"rats:{chat_id}", [])

    if any(r["username"].lower() == username.lower() for r in rats):
        await update.message.reply_text(f"{username} is already on the list. We know.")
        return

    rats.append({
        "username": username,
        "accused_by": _uname(update.effective_user),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    storage.set(f"rats:{chat_id}", rats)

    phrase = random.choice(_RAT_PHRASES).format(username=username)
    await update.message.reply_text(f"🐀 {phrase}")


@_group_only
async def unrat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "unrat"):
        return
    _, username = _parse_target(update, context)
    if not username:
        await update.message.reply_text(
            "Who we clearing? `/unrat @username`", parse_mode="Markdown"
        )
        return

    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id
    rats = storage.get(f"rats:{chat_id}", [])
    before = len(rats)
    rats = [r for r in rats if r["username"].lower() != username.lower()]

    if len(rats) == before:
        await update.message.reply_text(
            f"{username} wasn't on the list to begin with."
        )
        return

    storage.set(f"rats:{chat_id}", rats)
    phrase = random.choice(_UNRAT_PHRASES).format(username=username)
    await update.message.reply_text(f"✅ {phrase}")


@_group_only
async def rats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "rats"):
        return
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id
    rats = storage.get(f"rats:{chat_id}", [])

    if not rats:
        await update.message.reply_text(
            "🐀 The list is clean. Nobody's been calling us rats."
        )
        return

    lines = ["🐀 *Known Rats:*\n"]
    for r in rats:
        lines.append(f"• {r['username']} — fingered by {r['accused_by']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Rank system ──────────────────────────────────────────────────────────────────

@_group_only
async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "rank"):
        return
    storage = context.bot_data["storage"]
    user = update.effective_user
    chat_id = update.effective_chat.id

    rank = await _get_rank(context, chat_id, user.id, storage)
    emoji = _RANK_EMOJI[rank]
    flavor = _RANK_FLAVOR[rank]

    await update.message.reply_text(
        f"{emoji} *{_uname(user)}*\nRank: *{rank}*\n\n_{flavor}_",
        parse_mode="Markdown",
    )


@_group_only
async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "promote"):
        return
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id
    caller = update.effective_user

    caller_rank = await _get_rank(context, chat_id, caller.id, storage)
    if caller_rank not in ("Capo", "Underboss"):
        await update.message.reply_text(
            "⚠️ You ain't got the juice for that. Talk to a Capo."
        )
        return

    target_id, target_username = _parse_target(update, context)
    if not target_id:
        await update.message.reply_text(
            "Reply to their message to promote them. `/promote` (as a reply)",
            parse_mode="Markdown",
        )
        return

    target_rank = await _get_rank(context, chat_id, target_id, storage)
    if target_rank != "Associate":
        await update.message.reply_text(
            f"{target_username} is already {target_rank}. Nothing to do here."
        )
        return

    soldiers = storage.get(f"soldiers:{chat_id}", [])
    if not any(s.get("id") == target_id for s in soldiers):
        soldiers.append({"id": target_id, "username": target_username})
        storage.set(f"soldiers:{chat_id}", soldiers)

    await update.message.reply_text(
        f"⚔️ {target_username} — you've been made. Welcome to the Family, *Soldier*. "
        f"Don't make us regret it.",
        parse_mode="Markdown",
    )


@_group_only
async def family_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "family"):
        return
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    try:
        admins = await context.bot.get_chat_administrators(chat_id)
    except Exception:
        await update.message.reply_text(
            "Can't pull the family tree right now. Try again."
        )
        return

    underbosses = []
    capos = []
    for admin in admins:
        uname = _uname(admin.user)
        if admin.status == "creator":
            underbosses.append(f"👑 {uname} — *Underboss*")
        else:
            capos.append(f"🎖️ {uname} — *Capo*")

    soldiers = storage.get(f"soldiers:{chat_id}", [])
    soldier_lines = [
        f"⚔️ {s['username']} — *Soldier*"
        for s in soldiers
        if isinstance(s, dict) and s.get("username")
    ]

    lines = ["🔷 *The Family:*\n"]
    lines.extend(underbosses)
    lines.extend(capos)
    lines.extend(soldier_lines)
    if not any([underbosses, capos, soldier_lines]):
        lines.append("_Nobody's registered yet. Quiet like a Sunday._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Handler list ─────────────────────────────────────────────────────────────────

def build_social_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("rat",     rat_cmd),
        CommandHandler("unrat",   unrat_cmd),
        CommandHandler("rats",    rats_cmd),
        CommandHandler("rank",    rank_cmd),
        CommandHandler("promote", promote_cmd),
        CommandHandler("family",  family_cmd),
    ]
