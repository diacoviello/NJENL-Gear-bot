"""
sopranos.py
===========
Sopranos character quote drops.

  /tony [@username]        — Tony has a message
  /paulie [@username]      — Paulie's got something to say
  /christopher [@username]
  /silvio [@username]
  /junior [@username]
  /bobby [@username]
  /carmela [@username]

Omit @username for an undirected quote drop.
Reuses the load_quotes() parser from quotes.py against sopranos_quotes.txt.
"""

import os
import random

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from quotes import load_quotes
from topic_guard import topic_allowed

_QUOTES_FILE = os.path.join(os.path.dirname(__file__), "sopranos_quotes.txt")

CHARACTER_COMMANDS = ["tony", "paulie", "christopher", "silvio", "junior", "bobby", "carmela"]

_INTROS = [
    "{char} to {target}:",
    "{char}'s got a message for {target}:",
    "{char} wants {target} to hear this:",
    "{char}, on {target}:",
    "Word from {char}, directed at {target}:",
]

_INTROS_NO_TARGET = [
    "{char} says:",
    "{char}, unprompted:",
    "From the desk of {char}:",
    "{char} feels the need to share:",
]


def build_sopranos_handlers() -> list[CommandHandler]:
    quotes, display, _ = load_quotes(path=_QUOTES_FILE)

    async def character_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
        raw_cmd = update.message.text.split()[0].lstrip("/").split("@")[0].lower()

        if not topic_allowed(update, context, raw_cmd):
            return

        pool = quotes.get(raw_cmd)
        if not pool:
            await update.message.reply_text("That ain't one of our people.")
            return

        char_name = display.get(raw_cmd, raw_cmd.title())
        quote = random.choice(pool)

        if context.args:
            target = context.args[0]
            if not target.startswith("@"):
                target = "@" + target
            intro = random.choice(_INTROS).format(char=char_name, target=target)
        else:
            intro = random.choice(_INTROS_NO_TARGET).format(char=char_name)

        await update.message.reply_text(
            f"🔷 *{intro}*\n\n_{quote}_",
            parse_mode="Markdown",
        )

    return [CommandHandler(cmd, character_quote) for cmd in CHARACTER_COMMANDS]
