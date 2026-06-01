"""
lookups.py
==========
Read/close commands generated from the same FLOWS config:
  /needs [location]   /offers [location]   /filled <id>   /cancel <id>
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from topics import FLOWS


def build_list_handler(flow_key: str) -> CommandHandler:
    cfg = FLOWS[flow_key]

    async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
        storage = context.bot_data["storage"]
        loc_filter = " ".join(context.args).strip().lower() if context.args else ""

        items = [
            e for e in storage.list(cfg["store_key"])
            if e["status"] == cfg["list_status"]
        ]
        if loc_filter:
            items = [e for e in items if loc_filter in e["location"].lower()]

        if not items:
            if loc_filter:
                await update.message.reply_text(
                    f"No entries near *{loc_filter}*.", parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(cfg["list_empty"])
            return

        title = cfg["list_title"]
        if loc_filter:
            title += f" near {loc_filter}"
        lines = [f"{cfg['confirm_emoji']} *{title}:*\n"]
        for e in items:
            lines.append(
                f"*#{e['id']}* {e['username']}\n"
                f"  🔹 {cfg['label_have']}: {e['items']}\n"
                f"  📍 Near: {e['location']}\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    return CommandHandler(cfg["list_command"], show_list)


def build_close_handler(flow_key: str) -> CommandHandler:
    cfg = FLOWS[flow_key]
    closed_status = "filled" if flow_key == "need" else "cancelled"

    async def close_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        storage = context.bot_data["storage"]
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                f"Usage: `/{cfg['close_cmd']} <id>`", parse_mode="Markdown"
            )
            return

        entry_id = int(context.args[0])
        # find it first to verify ownership
        match = next(
            (e for e in storage.list(cfg["store_key"])
             if e["id"] == entry_id and e["status"] == cfg["status_default"]),
            None,
        )
        if not match:
            await update.message.reply_text(f"#{entry_id} not found or already closed.")
            return
        if match["user_id"] != update.effective_user.id:
            await update.message.reply_text("⚠️ You can only manage your own entries.")
            return

        storage.update_status(cfg["store_key"], entry_id, closed_status)
        await update.message.reply_text(
            f"✅ #{entry_id} marked as *{closed_status}*. 🔷", parse_mode="Markdown"
        )

    return CommandHandler(cfg["close_cmd"], close_entry)


def build_clear_handler(flow_key: str) -> CommandHandler:
    cfg = FLOWS[flow_key]
    closed_status = "filled" if flow_key == "need" else "cancelled"

    async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
        storage = context.bot_data["storage"]
        word = cfg["saved_word"].lower()
        count = storage.clear_user_entries(
            cfg["store_key"], update.effective_user.id,
            cfg["status_default"], closed_status,
        )
        if not count:
            await update.message.reply_text(f"You have no open {word}s to clear.")
            return
        await update.message.reply_text(
            f"🧹 Cleared *{count}* of your {word}s.", parse_mode="Markdown"
        )

    return CommandHandler(cfg["clear_cmd"], clear_all)
