"""
topic_guard.py
==============
Restricts every command to the Telegram forum topic it has been assigned to.

topic_allowed(update, context, command)
    Returns True only when the message arrives in the thread that command is
    assigned to.  Per-chat DB overrides take precedence over TOPIC_DEFAULTS.
    Commands with no assignment are blocked everywhere.
    Sentinel value -1 = "blocked everywhere, ignore defaults."

/settopic  — Capo / Underboss only
    Bare command (from inside a topic): shows an inline keyboard of all
    commands not yet assigned to that topic; tap one to assign it.
    /settopic list              — show all effective assignments (anyone)
    /settopic clear cmd1 cmd2  — block those commands everywhere

/removetopic — Capo / Underboss only
    Bare command: shows an inline keyboard of all current per-chat overrides;
    tap one to remove it (reverts to TOPIC_DEFAULTS or unblocked).

settopic and removetopic themselves are PROTECTED — they always work from
any topic or the main chat and cannot be reassigned or blocked.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from topics import TOPIC_DEFAULTS

_KEY = "topic_commands:{}"

# These commands are always reachable and cannot be assigned to a specific topic.
_PROTECTED = {"settopic", "removetopic", "start", "help"}

# Every command that CAN be assigned to a topic (shown in the keyboard).
ALL_ASSIGNABLE_COMMANDS = [
    # Gear & transport
    "need", "have", "needs", "offers",
    "filled", "cancel", "clearneeds", "clearoffers",
    "run", "runs", "delivered",
    # Smurf
    "smurf",
    # Sopranos drops
    "tony", "paulie", "christopher", "silvio", "junior", "bobby", "carmela",
    # Social
    "rat", "unrat", "rats", "rank", "promote", "family",
    # Pitch box 
    "pitch", "ideas", "unpitch",
]

_CHOOSE_ASSIGN = 0
_CHOOSE_REMOVE = 0  # separate ConversationHandlers — same int is fine


# ── Core guard ───────────────────────────────────────────────────────────────────

def topic_allowed(update: Update, context, command: str) -> bool:
    if command in _PROTECTED:
        return True
    msg = update.message or update.edited_message
    if not msg:
        return False
    chat_id   = update.effective_chat.id
    thread_id = msg.message_thread_id
    storage   = context.bot_data["storage"]
    overrides = storage.get(_KEY.format(chat_id), {})
    allowed   = overrides.get(command, TOPIC_DEFAULTS.get(command))
    if allowed is None or allowed == -1:
        return False
    return thread_id == allowed


async def topic_check(update: Update, context, command: str) -> bool:
    """Like topic_allowed but sends a response when the command is blocked."""
    if topic_allowed(update, context, command):
        return True
    msg = update.message or update.edited_message
    if msg and update.effective_chat.type != "private":
        await msg.reply_text(
            "Hey, we don't do that here. "
            "If you can quote the rules, then you can obey them."
        )
    return False


# ── Rank helper ───────────────────────────────────────────────────────────────────

async def _caller_rank(context, chat_id: int, user_id: int, storage) -> str:
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


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fuhgeddaboudit.")
    return ConversationHandler.END


# ── Keyboard builders ─────────────────────────────────────────────────────────────

def _assign_keyboard(storage, chat_id: int, thread_id: int) -> InlineKeyboardMarkup | None:
    """Buttons for commands NOT already assigned to thread_id."""
    overrides  = storage.get(_KEY.format(chat_id), {})
    available  = [
        cmd for cmd in ALL_ASSIGNABLE_COMMANDS
        if overrides.get(cmd, TOPIC_DEFAULTS.get(cmd)) != thread_id
    ]
    if not available:
        return None
    rows = [
        [InlineKeyboardButton(f"/{c}", callback_data=f"assign:{c}") for c in available[i:i+3]]
        for i in range(0, len(available), 3)
    ]
    rows.append([InlineKeyboardButton("✅ Done", callback_data="assign:done")])
    return InlineKeyboardMarkup(rows)


def _remove_keyboard(storage, chat_id: int) -> InlineKeyboardMarkup | None:
    """Buttons for commands that have a per-chat DB override (removable)."""
    overrides = storage.get(_KEY.format(chat_id), {})
    removable = [cmd for cmd in ALL_ASSIGNABLE_COMMANDS if cmd in overrides]
    if not removable:
        return None
    rows = [
        [InlineKeyboardButton(f"/{c}", callback_data=f"remove:{c}") for c in removable[i:i+3]]
        for i in range(0, len(removable), 3)
    ]
    rows.append([InlineKeyboardButton("✅ Done", callback_data="remove:done")])
    return InlineKeyboardMarkup(rows)


# ── /settopic shared logic ────────────────────────────────────────────────────────

def _show_list(storage, chat_id: int) -> str:
    overrides = storage.get(_KEY.format(chat_id), {})
    merged    = {**TOPIC_DEFAULTS, **{k: v for k, v in overrides.items() if v != -1}}
    blocked   = [k for k, v in overrides.items() if v == -1]
    by_topic: dict[int, list[str]] = {}
    for cmd, tid in sorted(merged.items()):
        by_topic.setdefault(tid, []).append(f"`/{cmd}`")
    lines = ["📋 *Effective Topic Assignments:*\n"]
    for tid, cmds in sorted(by_topic.items()):
        lines.append(f"*Thread {tid}:* {', '.join(cmds)}")
    if blocked:
        lines.append(f"\n🚫 *Blocked everywhere:* {', '.join(f'`/{c}`' for c in blocked)}")
    if not merged and not blocked:
        lines.append("_No assignments set. Built-in defaults apply._")
    return "\n".join(lines)


async def _process_settopic(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]):
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    if args == ["list"]:
        await update.message.reply_text(_show_list(storage, chat_id), parse_mode="Markdown")
        return

    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
        return

    # Filter out protected commands silently
    safe_args = [a for a in args if a not in _PROTECTED]

    if args and args[0] == "clear":
        targets = [a for a in args[1:] if a not in _PROTECTED]
        if not targets:
            await update.message.reply_text(
                "Clear what exactly? You gotta give me names. Send: `clear cmd1 cmd2`",
                parse_mode="Markdown",
            )
            return
        overrides = storage.get(_KEY.format(chat_id), {})
        for cmd in targets:
            overrides[cmd] = -1
        storage.set(_KEY.format(chat_id), overrides)
        cleared = ", ".join(f"`/{c}`" for c in targets)
        await update.message.reply_text(
            f"🚫 {cleared} — blocked everywhere. "
            f"Use `/settopic {' '.join(targets)}` from a topic to reassign.",
            parse_mode="Markdown",
        )
        return

    thread_id = update.message.message_thread_id
    if not thread_id:
        await update.message.reply_text(
            "Run this from *inside* a topic, not the main chat.", parse_mode="Markdown"
        )
        return

    if not safe_args:
        return

    overrides = storage.get(_KEY.format(chat_id), {})
    for cmd in safe_args:
        overrides[cmd] = thread_id
    storage.set(_KEY.format(chat_id), overrides)
    assigned = ", ".join(f"`/{c}`" for c in safe_args)
    await update.message.reply_text(
        f"✅ Assigned to thread {thread_id}: {assigned}", parse_mode="Markdown"
    )


# ── /settopic ConversationHandler ─────────────────────────────────────────────────

def build_settopic_handler() -> ConversationHandler:
    async def settopic_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return ConversationHandler.END

        args = [a.lstrip("/").lower() for a in (context.args or [])]
        if args:
            await _process_settopic(update, context, args)
            return ConversationHandler.END

        # Bare /settopic — show button menu
        thread_id = update.message.message_thread_id
        if not thread_id:
            await update.message.reply_text(
                "You gotta run this from *inside* a topic, not the main chat.\n"
                "Or use `/settopic list` to see current assignments.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        storage = context.bot_data["storage"]
        chat_id = update.effective_chat.id
        rank    = await _caller_rank(context, chat_id, update.effective_user.id, storage)
        if rank not in ("Capo", "Underboss"):
            await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
            return ConversationHandler.END

        kb = _assign_keyboard(storage, chat_id, thread_id)
        if kb is None:
            await update.message.reply_text(
                "Every command is already assigned to this topic. We're all set here."
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Which command you assignin' to this topic? Pick one.",
            reply_markup=kb,
        )
        return _CHOOSE_ASSIGN

    async def choose_assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "assign:done":
            await query.edit_message_text("Alright, we're done here. Capisce?")
            return ConversationHandler.END

        cmd       = data.split(":", 1)[1]
        thread_id = query.message.message_thread_id
        chat_id   = update.effective_chat.id
        storage   = context.bot_data["storage"]

        overrides        = storage.get(_KEY.format(chat_id), {})
        overrides[cmd]   = thread_id
        storage.set(_KEY.format(chat_id), overrides)

        kb = _assign_keyboard(storage, chat_id, thread_id)
        if kb is None:
            await query.edit_message_text(
                f"✅ `/{cmd}` assigned. That's every command locked to this topic. We're done.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        await query.edit_message_text(
            f"✅ `/{cmd}` assigned. Anything else?",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return _CHOOSE_ASSIGN

    return ConversationHandler(
        entry_points=[CommandHandler("settopic", settopic_entry)],
        states={_CHOOSE_ASSIGN: [CallbackQueryHandler(choose_assign, pattern="^assign:")]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )


# ── /removetopic ConversationHandler ─────────────────────────────────────────────

async def _process_removetopic(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]):
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
        return

    safe_args = [a for a in args if a not in _PROTECTED]
    overrides = storage.get(_KEY.format(chat_id), {})
    removed, unknown = [], []
    for cmd in safe_args:
        if cmd in overrides:
            del overrides[cmd]
            removed.append(cmd)
        else:
            unknown.append(cmd)
    storage.set(_KEY.format(chat_id), overrides)

    lines = []
    if removed:
        reverted = []
        for cmd in removed:
            default = TOPIC_DEFAULTS.get(cmd)
            suffix  = f"→ reverts to thread {default}" if default else "→ now blocked (no default)"
            reverted.append(f"`/{cmd}` {suffix}")
        lines.append("✅ *Removed overrides:*\n" + "\n".join(reverted))
    if unknown:
        lines.append(
            "ℹ️ *No override found for:* "
            + ", ".join(f"`/{c}`" for c in unknown)
            + " — nothing to remove."
        )
    if lines:
        await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


def build_removetopic_handler() -> ConversationHandler:
    async def removetopic_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return ConversationHandler.END

        args = [a.lstrip("/").lower() for a in (context.args or [])]
        if args:
            await _process_removetopic(update, context, args)
            return ConversationHandler.END

        storage = context.bot_data["storage"]
        chat_id = update.effective_chat.id
        rank    = await _caller_rank(context, chat_id, update.effective_user.id, storage)
        if rank not in ("Capo", "Underboss"):
            await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
            return ConversationHandler.END

        kb = _remove_keyboard(storage, chat_id)
        if kb is None:
            await update.message.reply_text(
                "No overrides to pull. Everything's runnin' on the defaults, Capisce?"
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Which override you pullin'? Pick one.",
            reply_markup=kb,
        )
        return _CHOOSE_REMOVE

    async def choose_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "remove:done":
            await query.edit_message_text("Alright, we're done here. Capisce?")
            return ConversationHandler.END

        cmd     = data.split(":", 1)[1]
        chat_id = update.effective_chat.id
        storage = context.bot_data["storage"]

        overrides = storage.get(_KEY.format(chat_id), {})
        if cmd in overrides:
            del overrides[cmd]
            storage.set(_KEY.format(chat_id), overrides)

        default = TOPIC_DEFAULTS.get(cmd)
        suffix  = f"reverts to thread {default}" if default else "now blocked everywhere"

        kb = _remove_keyboard(storage, chat_id)
        if kb is None:
            await query.edit_message_text(
                f"✅ `/{cmd}` pulled — {suffix}. That's all the overrides, we're clean.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        await query.edit_message_text(
            f"✅ `/{cmd}` pulled — {suffix}.\n\nAnything else you pullin'?",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return _CHOOSE_REMOVE

    return ConversationHandler(
        entry_points=[CommandHandler("removetopic", removetopic_entry)],
        states={_CHOOSE_REMOVE: [CallbackQueryHandler(choose_remove, pattern="^remove:")]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )
