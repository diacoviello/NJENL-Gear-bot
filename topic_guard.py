"""
topic_guard.py
==============
Restricts every command to the Telegram forum topic it has been assigned to.

topic_allowed(update, context, command)
    Returns True only when the message arrives in the thread that command is
    assigned to.  Per-chat DB overrides take precedence over TOPIC_DEFAULTS
    (defined in topics.py).  Commands with no assignment are blocked everywhere.

    Sentinel value -1 stored in the DB means "blocked everywhere, ignore defaults"
    — useful if a Capo wants to fully disable a built-in default.

/settopic   — Capo / Underboss only
    /settopic cmd1 cmd2 ...     assign those commands to the current topic
    /settopic clear cmd1 cmd2   block everywhere (overrides defaults)
    /settopic list              show all effective assignments (anyone)

/removetopic — Capo / Underboss only
    /removetopic cmd1 cmd2 ...  delete per-chat override; reverts to default
                                (or stays blocked if command has no default)

Both /settopic and /removetopic use ConversationHandlers: if arguments are
omitted the bot asks for them and waits for a text reply.
"""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from topics import TOPIC_DEFAULTS

# Storage key template for per-chat overrides
_KEY = "topic_commands:{}"

_ASK_SETTOPIC   = 0
_ASK_REMOVETOPIC = 0  # separate ConversationHandlers


# ── Core guard ───────────────────────────────────────────────────────────────────

def topic_allowed(update: Update, context, command: str) -> bool:
    msg = update.message or update.edited_message
    if not msg:
        return False
    chat_id   = update.effective_chat.id
    thread_id = msg.message_thread_id          # None when not inside a topic
    storage   = context.bot_data["storage"]
    overrides = storage.get(_KEY.format(chat_id), {})
    # DB override wins; fall back to hard-coded default; absent → blocked
    allowed   = overrides.get(command, TOPIC_DEFAULTS.get(command))
    if allowed is None or allowed == -1:       # unset or explicitly blocked
        return False
    return thread_id == allowed


# ── Rank helper (mirrors social.py without creating a circular import) ────────────

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


# ── /settopic ─────────────────────────────────────────────────────────────────────

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
    """Core settopic logic, shared by direct and conversational paths."""
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    if args == ["list"]:
        await update.message.reply_text(_show_list(storage, chat_id), parse_mode="Markdown")
        return

    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
        return

    if args and args[0] == "clear":
        targets = args[1:]
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
            f"Use `/settopic {' '.join(targets)}` from inside a topic to reassign.",
            parse_mode="Markdown",
        )
        return

    thread_id = update.message.message_thread_id
    if not thread_id:
        await update.message.reply_text(
            "Run this from *inside* a topic, not the main chat.", parse_mode="Markdown"
        )
        return

    overrides = storage.get(_KEY.format(chat_id), {})
    for cmd in args:
        overrides[cmd] = thread_id
    storage.set(_KEY.format(chat_id), overrides)
    assigned = ", ".join(f"`/{c}`" for c in args)
    await update.message.reply_text(
        f"✅ Assigned to thread {thread_id}: {assigned}", parse_mode="Markdown"
    )


def build_settopic_handler() -> ConversationHandler:
    async def settopic_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return ConversationHandler.END
        args = [a.lstrip("/").lower() for a in (context.args or [])]
        if args:
            await _process_settopic(update, context, args)
            return ConversationHandler.END
        # Bare /settopic — ask what they want
        await update.message.reply_text(
            "Whaddya want? Send me one of these:\n\n"
            "`list` — show what's assigned\n"
            "`clear cmd1 cmd2` — block those commands everywhere\n"
            "`cmd1 cmd2` — lock 'em to this topic\n\n"
            "_Or /cancel._",
            parse_mode="Markdown",
        )
        return _ASK_SETTOPIC

    async def settopic_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = [a.lstrip("/").lower() for a in update.message.text.strip().split()]
        if not args:
            await update.message.reply_text("I need somethin' to work with here. Send it or /cancel.")
            return _ASK_SETTOPIC
        await _process_settopic(update, context, args)
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("settopic", settopic_entry)],
        states={_ASK_SETTOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, settopic_receive)]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )


# ── /removetopic ─────────────────────────────────────────────────────────────────

async def _process_removetopic(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]):
    """Core removetopic logic, shared by direct and conversational paths."""
    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text("⚠️ You ain't got the juice for that. Talk to a Capo.")
        return

    overrides = storage.get(_KEY.format(chat_id), {})
    removed, unknown = [], []
    for cmd in args:
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
            suffix = f"→ reverts to thread {default}" if default else "→ now blocked (no default)"
            reverted.append(f"`/{cmd}` {suffix}")
        lines.append("✅ *Removed overrides:*\n" + "\n".join(reverted))
    if unknown:
        lines.append(
            "ℹ️ *No override found for:* "
            + ", ".join(f"`/{c}`" for c in unknown)
            + " — nothing to remove."
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


def build_removetopic_handler() -> ConversationHandler:
    async def removetopic_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return ConversationHandler.END
        args = [a.lstrip("/").lower() for a in (context.args or [])]
        if args:
            await _process_removetopic(update, context, args)
            return ConversationHandler.END
        await update.message.reply_text(
            "Which overrides you pullin'? Send the command names, space 'em out.\n"
            "_(e.g. `rat unrat tony`)_\n\n"
            "Hit `/settopic list` if you don't remember what's set.\n"
            "Or /cancel.",
            parse_mode="Markdown",
        )
        return _ASK_REMOVETOPIC

    async def removetopic_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = [a.lstrip("/").lower() for a in update.message.text.strip().split()]
        if not args:
            await update.message.reply_text("Send the command names. Don't bust my balls. Or /cancel.")
            return _ASK_REMOVETOPIC
        await _process_removetopic(update, context, args)
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("removetopic", removetopic_entry)],
        states={_ASK_REMOVETOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, removetopic_receive)]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )
