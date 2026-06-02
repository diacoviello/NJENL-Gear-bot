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
                    f"In *{loc_filter}*? Oogatz here, I got nothin' for ya.", parse_mode="Markdown"
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
                f"Cut the crap. What's the number?: `/{cfg['close_cmd']} <id>`", parse_mode="Markdown"
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
            await update.message.reply_text(f"#{entry_id}? Never heard of it. Or it's already handled.")
            return
        if match["user_id"] != update.effective_user.id:
            await update.message.reply_text("⚠️ Hey. You don't touch what ain't yours. Capisce?")
            return

        storage.update_status(cfg["store_key"], entry_id, closed_status)
        await update.message.reply_text(
            f"✅ the matter of #{entry_id} is *{closed_status}*. That's the end of it. 🔷", parse_mode="Markdown"
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
            await update.message.reply_text(f"You got no open {word}s to clear. What’s the matter with you?")
            return
        await update.message.reply_text(
            f"🧹 Wiped *{count}* of your {word}s off the books. Like they never existed.",
            parse_mode="Markdown",
        )

    return CommandHandler(cfg["clear_cmd"], clear_all)
