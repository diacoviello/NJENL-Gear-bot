"""
bot.py
======
Entry point. Wires up every flow defined in topics.py:
  - a ConversationHandler   (/need, /have)
  - a list command          (/needs, /offers)
  - a close command         (/filled, /cancel)

Run:
    export BOT_TOKEN="..."   (or put it in a .env file)
    python bot.py
"""

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from storage import Storage
from topics import FLOWS
from conversation import build_flow_handler
from lookups import build_list_handler, build_close_handler, build_clear_handler
from quotes import build_quote_handler

# Optional: load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Global commands ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Agent"
    await update.message.reply_text(
        f"🔷 *Ay, {name}. Welcome to this thing of ours.*\n\n"
        "You need somethin', you got somethin'? You come to me. "
        "If there’s a problem, hit /help and I'll lay it all out for ya. Don’t involve anybody else.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🔷 *Here's how it works around here. Capisce?*\n"]
    for cfg in FLOWS.values():
        lines.append(
            f"`/{cfg['command']}` — put in your {cfg['saved_word'].lower()}\n"
            f"`/{cfg['list_command']} [location]` — see {cfg['list_title'].lower()}\n"
            f"`/{cfg['close_cmd']} <id>` — mark one handled, fuhgeddaboudit\n"
            f"`/{cfg['clear_cmd']}` — wipe all your {cfg['saved_word'].lower()}s off the books\n"
        )
    lines.append(
        "\n_Quick like, for the busy man:_\n"
        "`/need L8 XMPs near Caldwell` — done, no back-and-forth\n"
        "`/need near Newark` — start me off with the spot"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Main ──────────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the BOT_TOKEN environment variable (or put it in .env).")

    app = Application.builder().token(token).build()
    # DB_PATH lets prod point at a persistent volume (e.g. /data/ingress_bot.db);
    # defaults to a local file for development.
    app.bot_data["storage"] = Storage(os.environ.get("DB_PATH", "ingress_bot.db"))

    # Global commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # Build everything from the FLOWS config
    for flow_key in FLOWS:
        app.add_handler(build_flow_handler(flow_key))   # /need, /have
        app.add_handler(build_list_handler(flow_key))   # /needs, /offers
        app.add_handler(build_close_handler(flow_key))  # /filled, /cancel
        app.add_handler(build_clear_handler(flow_key))  # /clearneeds, /clearoffers

    # Easter egg: /<agentname> → random quote. Registered LAST so it only
    # fires for commands no real handler claimed.
    app.add_handler(build_quote_handler())

    logger.info("Bot started. Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
