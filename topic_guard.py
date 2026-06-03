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

/settopic — Capo / Underboss only
    /settopic cmd1 cmd2 ...     assign those commands to the current topic
    /settopic clear cmd1 cmd2   unassign (block everywhere, overriding defaults)
    /settopic list              show all effective assignments for this chat
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from topics import TOPIC_DEFAULTS

# Storage key template for per-chat overrides
_KEY = "topic_commands:{}"


# ── Core guard ───────────────────────────────────────────────────────────────────

def topic_allowed(update: Update, context, command: str) -> bool:
    msg = update.message or update.edited_message
    if not msg:
        return False

    chat_id  = update.effective_chat.id
    thread_id = msg.message_thread_id          # None when not inside a topic

    storage     = context.bot_data["storage"]
    overrides   = storage.get(_KEY.format(chat_id), {})

    # DB override wins; fall back to hard-coded default; absent → blocked
    allowed = overrides.get(command, TOPIC_DEFAULTS.get(command))

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


# ── /settopic ────────────────────────────────────────────────────────────────────

async def settopic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "Topics only exist in group chats. Take this to the group."
        )
        return

    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id
    args    = [a.lstrip("/").lower() for a in (context.args or [])]

    # ── /settopic list ─────────────────────────────────────────────────────────
    if args == ["list"]:
        overrides = storage.get(_KEY.format(chat_id), {})
        merged    = {**TOPIC_DEFAULTS, **{k: v for k, v in overrides.items() if v != -1}}
        blocked   = [k for k, v in overrides.items() if v == -1]

        if not merged and not blocked:
            await update.message.reply_text(
                "No topic assignments in this chat. Built-in defaults apply."
            )
            return

        by_topic: dict[int, list[str]] = {}
        for cmd, tid in sorted(merged.items()):
            by_topic.setdefault(tid, []).append(f"`/{cmd}`")

        lines = ["📋 *Effective Topic Assignments:*\n"]
        for tid, cmds in sorted(by_topic.items()):
            marker = " _(default)_" if all(
                TOPIC_DEFAULTS.get(c.strip("`/")) == tid and c.strip("`/") not in overrides
                for c in cmds
            ) else ""
            lines.append(f"*Thread {tid}:*{marker} {', '.join(cmds)}")
        if blocked:
            lines.append(f"\n🚫 *Blocked everywhere:* {', '.join(f'`/{c}`' for c in blocked)}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # All write operations require Capo or above
    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text(
            "⚠️ You ain't got the juice for that. Talk to a Capo."
        )
        return

    # ── /settopic clear cmd1 cmd2 ─────────────────────────────────────────────
    if args and args[0] == "clear":
        targets = args[1:]
        if not targets:
            await update.message.reply_text(
                "Clear what? `/settopic clear cmd1 cmd2`", parse_mode="Markdown"
            )
            return

        overrides = storage.get(_KEY.format(chat_id), {})
        cleared   = []
        for cmd in targets:
            overrides[cmd] = -1          # sentinel: blocked everywhere
            cleared.append(f"`/{cmd}`")
        storage.set(_KEY.format(chat_id), overrides)

        await update.message.reply_text(
            f"🚫 {', '.join(cleared)} — blocked everywhere. "
            f"Use `/settopic {' '.join(targets)}` from a topic to reassign.",
            parse_mode="Markdown",
        )
        return

    # ── /settopic cmd1 cmd2 — assign to current topic ────────────────────────
    thread_id = update.message.message_thread_id
    if not thread_id:
        await update.message.reply_text(
            "Run this command from *inside* a topic, not the main chat.",
            parse_mode="Markdown",
        )
        return

    if not args:
        await update.message.reply_text(
            "Which commands?\n"
            "`/settopic cmd1 cmd2 ...` — assign to this topic\n"
            "`/settopic list` — see all current assignments\n"
            "`/settopic clear cmd1 cmd2` — block a command everywhere",
            parse_mode="Markdown",
        )
        return

    overrides = storage.get(_KEY.format(chat_id), {})
    for cmd in args:
        overrides[cmd] = thread_id
    storage.set(_KEY.format(chat_id), overrides)

    assigned = ", ".join(f"`/{c}`" for c in args)
    await update.message.reply_text(
        f"✅ Assigned to thread {thread_id}: {assigned}",
        parse_mode="Markdown",
    )


def build_settopic_handler() -> CommandHandler:
    return CommandHandler("settopic", settopic_cmd)


# ── /removetopic ─────────────────────────────────────────────────────────────────

async def removetopic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove per-chat DB overrides for the listed commands.

    The command reverts to TOPIC_DEFAULTS if it has a built-in default, or
    stays blocked if it never had one.  This is different from /settopic clear,
    which writes a -1 sentinel that blocks even built-in defaults.
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("Topics only exist in group chats.")
        return

    storage = context.bot_data["storage"]
    chat_id = update.effective_chat.id

    rank = await _caller_rank(context, chat_id, update.effective_user.id, storage)
    if rank not in ("Capo", "Underboss"):
        await update.message.reply_text(
            "⚠️ You ain't got the juice for that. Talk to a Capo."
        )
        return

    args = [a.lstrip("/").lower() for a in (context.args or [])]
    if not args:
        await update.message.reply_text(
            "Which commands? `/removetopic cmd1 cmd2 ...`", parse_mode="Markdown"
        )
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


def build_removetopic_handler() -> CommandHandler:
    return CommandHandler("removetopic", removetopic_cmd)
