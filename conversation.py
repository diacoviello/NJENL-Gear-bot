# noinspection SpellCheckingInspection
"""
conversation.py
================
Builds a Telegram ConversationHandler for each flow defined in topics.py.

The flow (identical for /need and /have):

    /need
      → CHOOSE_GEAR   (gear type buttons)
          ├─ leveled gear → CHOOSE_LEVEL  (level buttons)  → ASK_LOCATION
          ├─ Mods         → CHOOSE_MOD    (mod buttons)    → ASK_LOCATION
          └─ Other        → DEFINE_OTHER  (free text)      → ASK_LOCATION
      → ASK_LOCATION (free text)  → save

Shortcut entry styles (parsed in the /command entry point):
    /need near Paramus            → button flow, location pre-filled
    /need L8 XMPs                 → skip to location prompt
    /need L8 XMPs near Asbury    → save immediately
"""

import re
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from topics import GEAR_TYPES, LEVELS, MOD_TYPES, LEVELED_GEAR, LEVEL_OPTIONS, FLOWS
from matching import notify_matches
from topic_guard import topic_allowed

# Conversation states
CHOOSE_GEAR, CHOOSE_LEVEL, CHOOSE_MOD, DEFINE_OTHER, ASK_LOCATION = range(5)

# Regex to split "items near location"
_FULL_RE = re.compile(r"^(.+?)\s+(?:near|in|around|at|by)\s+(.+)$", re.IGNORECASE)
_LOC_RE = re.compile(r"^(?:near|in|around|at|by)\s+(.+)$", re.IGNORECASE)


# ── Keyboard builders ───────────────────────────────────────────────────────────

def _keyboard(options: list[str], per_row: int = 2) -> InlineKeyboardMarkup:
    rows, row = [], []
    for opt in options:
        row.append(InlineKeyboardButton(opt, callback_data=opt))
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _username(update: Update) -> str:
    u = update.effective_user
    return f"@{u.username}" if u.username else u.full_name


# ── Save + confirm ───────────────────────────────────────────────────────────────

def _save_and_confirm(context, flow_key: str, user, items: str, location: str) -> tuple[str, dict]:
    cfg = FLOWS[flow_key]
    storage = context.bot_data["storage"]

    entry_id = storage.next_id(cfg["id_key"])
    username = f"@{user.username}" if user.username else user.full_name
    entry = {
        "id": entry_id,
        "user_id": user.id,
        "username": username,
        "items": items,
        "location": location,
        "status": cfg["status_default"],
        "created": datetime.now(timezone.utc).isoformat(),
    }
    storage.append(cfg["store_key"], entry)

    msg = (
        f"✅ *{cfg['saved_word']} #{entry_id} is on the books. I'll take care of it.*\n"
        f"👤 *Whose:* {username}\n"
        f"🔹 *{cfg['label_have']}:* {items}\n"
        f"📍 *Where:* {location}\n\n"
        f"When the job's done, hit `/{cfg['close_cmd']} {entry_id}`. You steer the ship the best way you know."
    )
    return msg, entry


# ── Factory: build one ConversationHandler for a flow ─────────────────────────────

def build_flow_handler(flow_key: str) -> ConversationHandler:
    cfg = FLOWS[flow_key]

    # ENTRY POINT — /need or /have, with optional inline shortcut text
    async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not topic_allowed(update, context, cfg["command"]):
            return ConversationHandler.END

        context.user_data.clear()
        context.user_data["flow"] = flow_key

        text = " ".join(context.args).strip() if context.args else ""

        # Full one-liner → save immediately
        m = _FULL_RE.match(text)
        if m:
            msg, entry = _save_and_confirm(context, flow_key, update.effective_user,
                                           m.group(1).strip(), m.group(2).strip())
            await update.message.reply_text(msg, parse_mode="Markdown")
            await notify_matches(context.bot, context.bot_data["storage"], flow_key, entry)
            return ConversationHandler.END

        # Location only → run button flow, remember location
        m = _LOC_RE.match(text)
        if m:
            context.user_data["location"] = m.group(1).strip()
            await update.message.reply_text(
                cfg["verb_prompt"], reply_markup=_keyboard(GEAR_TYPES)
            )
            return CHOOSE_GEAR

        # Gear text only → skip straight to location
        if text:
            context.user_data["items"] = text
            await update.message.reply_text(
                "📍 Where you at? Don't bust my balls — gimme a real spot. _(e.g. Hoboken, NJ)_",
                parse_mode="Markdown",
            )
            return ASK_LOCATION

        # Bare /need → full button flow
        await update.message.reply_text(
            cfg["verb_prompt"], reply_markup=_keyboard(GEAR_TYPES)
        )
        return CHOOSE_GEAR

    # STEP — gear type chosen
    async def choose_gear(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        choice = query.data
        context.user_data["gear_type"] = choice

        if choice in LEVELED_GEAR:
            levels = LEVEL_OPTIONS.get(choice, LEVELS)
            await query.edit_message_text(
                f"🔹 What level {choice}? Don't make me ask twice.",
                reply_markup=_keyboard(levels, per_row=4),
            )
            return CHOOSE_LEVEL

        if choice == "Mods":
            await query.edit_message_text(
                "🔧 What kinda mod we talkin'?", reply_markup=_keyboard(MOD_TYPES)
            )
            return CHOOSE_MOD

        # Other
        # noinspection SpellCheckingInspection
        await query.edit_message_text("✏️ What're you gettin' at? Send it in a message:")
        return DEFINE_OTHER

    # STEP — level chosen
    async def choose_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        gear = context.user_data["gear_type"]
        context.user_data["items"] = f"{gear} ({query.data})"
        return await _after_items(query, context)

    # STEP — mod chosen
    async def choose_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        context.user_data["items"] = f"Mods — {query.data}"
        return await _after_items(query, context)

    # STEP — free-text "other"
    async def define_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["items"] = update.message.text.strip()
        # No pre-filled location possible here unless one-liner; ask normally
        if context.user_data.get("location"):
            msg, entry = _save_and_confirm(context, flow_key, update.effective_user,
                                           context.user_data["items"], context.user_data["location"])
            await update.message.reply_text(msg, parse_mode="Markdown")
            await notify_matches(context.bot, context.bot_data["storage"], flow_key, entry)
            return ConversationHandler.END
        await update.message.reply_text(
            "📍 Where you at? Don't bust my balls — gimme a real spot. _(e.g. Wayne, NJ)_",
            parse_mode="Markdown",
        )
        return ASK_LOCATION

    # Shared: after items are known, either save (location pre-filled) or ask
    async def _after_items(query, context):
        if context.user_data.get("location"):
            msg, entry = _save_and_confirm(context, flow_key, query.from_user,
                                           context.user_data["items"], context.user_data["location"])
            await query.edit_message_text(msg, parse_mode="Markdown")
            await notify_matches(context.bot, context.bot_data["storage"], flow_key, entry)
            return ConversationHandler.END
        await query.edit_message_text(
            "📍 Where you at? Send it in a message, and gimme a real spot. _(e.g. Edison, NJ)_",
            parse_mode="Markdown",
        )
        return ASK_LOCATION

    # STEP — location entered
    async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
        location = update.message.text.strip()
        items = context.user_data.get("items")
        if not items:
            # noinspection SpellCheckingInspection
            await update.message.reply_text("⚠️ Marone. Somethin' went sideways. Start over.")
            context.user_data.clear()
            return ConversationHandler.END
        msg, entry = _save_and_confirm(context, flow_key, update.effective_user, items, location)
        await update.message.reply_text(msg, parse_mode="Markdown")
        await notify_matches(context.bot, context.bot_data["storage"], flow_key, entry)
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await update.message.reply_text("Fuhgeddaboudit. It's off the table.")
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler(cfg["command"], entry)],
        states={
            CHOOSE_GEAR:  [CallbackQueryHandler(choose_gear)],
            CHOOSE_LEVEL: [CallbackQueryHandler(choose_level)],
            CHOOSE_MOD:   [CallbackQueryHandler(choose_mod)],
            DEFINE_OTHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, define_other)],
            ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_location)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        # Let other commands interrupt the flow cleanly
        allow_reentry=True,
    )
