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
from lookups import build_list_handler, build_close_handler

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
        f"🔷 *Welcome to the Ingress Group Bot, {name}!*\n\nUse /help to see all commands.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🔷 *Ingress Group Bot — Commands*\n"]
    for cfg in FLOWS.values():
        lines.append(
            f"`/{cfg['command']}` — guided ({cfg['saved_word'].lower()})\n"
            f"`/{cfg['list_command']} [location]` — view {cfg['list_title'].lower()}\n"
            f"`/{cfg['close_cmd']} <id>` — close your entry\n"
        )
    lines.append(
        "\n_Shortcuts:_\n"
        "`/need L8 XMPs near Paramus` — save instantly\n"
        "`/need near Paramus` — pre-fill location"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Main ──────────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the BOT_TOKEN environment variable (or put it in .env).")

    app = Application.builder().token(token).build()
    app.bot_data["storage"] = Storage("ingress_bot.db")

    # Global commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # Build everything from the FLOWS config
    for flow_key in FLOWS:
        app.add_handler(build_flow_handler(flow_key))   # /need, /have
        app.add_handler(build_list_handler(flow_key))   # /needs, /offers
        app.add_handler(build_close_handler(flow_key))  # /filled, /cancel

    logger.info("Bot started. Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
