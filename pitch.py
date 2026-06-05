"""
pitch.py
========
Feature-idea pitch box. Agents float ideas for new bot features.

  /pitch <idea>   — drop an idea straight in
  /pitch          — bot asks for it (in true Sopranos fashion); reply with the idea
  /ideas          — list every pitch on the books
  /unpitch <id>   — pull a pitch (your own, or any if you're a Capo/Underboss)

Pitches live in a single global 'feature_pitches' bucket, so an idea floated
in one chat shows up wherever /ideas is run. Removal is a soft delete (status
flipped to 'removed') to mirror the gear-close flow. These commands are NOT
topic-guarded — like /start and /help they work anywhere, including DMs.
"""

import random
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

_STORE_KEY = "feature_pitches"
_ID_KEY    = "feature_pitch_next_id"

_ASK_PITCH = 0

_PITCH_PROMPTS = [
    "Alright, you got an idea? Let's hear it. What's this thing gonna do for the Family?",
    "Talk to me. What's the big idea you wanna float?",
    "You came to me with somethin', so out with it — what's the pitch?",
    "Okay, okay, I'm listenin'. What's this new feature you're dreamin' up?",
    "A new idea, huh? This better be good. Whaddya got?",
]

_SAVE_LINES = [
    "Good. I wrote it down. We'll look into it.",
    "Noted. Don't get excited — but it's on the books now.",
    "Alright, I like the way you think. It's filed.",
    "Consider it logged. We'll see if it's got legs.",
    "That's on the record now. Capisce?",
]


def _uname(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fuhgeddaboudit.")
    return ConversationHandler.END


async def _can_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, pitch: dict) -> bool:
    """The pitcher can pull their own; a group admin (Capo/Underboss) can pull any."""
    user = update.effective_user
    if pitch.get("user_id") == user.id:
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


async def _do_pitch(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    storage  = context.bot_data["storage"]
    pitch_id = storage.next_id(_ID_KEY)
    storage.append(_STORE_KEY, {
        "id":       pitch_id,
        "user_id":  update.effective_user.id,
        "username": _uname(update.effective_user),
        "text":     text,
        "status":   "open",
        "created":  datetime.now(timezone.utc).isoformat(),
    })
    await update.message.reply_text(
        f"💡 *Pitch #{pitch_id} — {random.choice(_SAVE_LINES)}*\n\n_{text}_",
        parse_mode="Markdown",
    )


# ── /pitch (drop-in or ask) ────────────────────────────────────────────────────────

def build_pitch_handler() -> ConversationHandler:
    async def pitch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.args:
            text = " ".join(context.args).strip()
            if text:
                await _do_pitch(update, context, text)
                return ConversationHandler.END
        await update.message.reply_text(random.choice(_PITCH_PROMPTS))
        return _ASK_PITCH

    async def pitch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if not text:
            await update.message.reply_text("That's nothin'. Gimme a real idea, or /cancel.")
            return _ASK_PITCH
        await _do_pitch(update, context, text)
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("pitch", pitch_entry)],
        states={_ASK_PITCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, pitch_receive)]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )


# ── /ideas ─────────────────────────────────────────────────────────────────────────

async def ideas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage = context.bot_data["storage"]
    pitches = [p for p in storage.list(_STORE_KEY) if p.get("status") == "open"]
    if not pitches:
        await update.message.reply_text(
            "💡 No ideas on the books. What, nobody's thinkin' around here? Float one with /pitch."
        )
        return
    lines = ["💡 *Ideas on the Table:*\n"]
    for p in pitches:
        lines.append(f"*#{p['id']}* — {p['text']}\n  _floated by {p['username']}_\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /unpitch <id> ───────────────────────────────────────────────────────────────────

async def unpitch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Which idea we killin'? Send me the number. `/unpitch <id>`\n"
            "_(Check `/ideas` if you forgot the number.)_",
            parse_mode="Markdown",
        )
        return
    pitch_id = int(context.args[0])
    storage  = context.bot_data["storage"]
    match = next(
        (p for p in storage.list(_STORE_KEY)
         if p["id"] == pitch_id and p.get("status") == "open"),
        None,
    )
    if not match:
        await update.message.reply_text(f"#{pitch_id}? Never heard of it. Or it's already gone.")
        return
    if not await _can_remove(update, context, match):
        await update.message.reply_text("⚠️ That ain't your idea to kill. Capisce?")
        return
    storage.update_status(_STORE_KEY, pitch_id, "removed")
    await update.message.reply_text(f"🗑️ Pitch #{pitch_id} is dead and buried. Fuhgeddaboudit.")


def build_pitch_handlers() -> list:
    return [
        build_pitch_handler(),
        CommandHandler("ideas",   ideas_cmd),
        CommandHandler("unpitch", unpitch_cmd),
    ]
