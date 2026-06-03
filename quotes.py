"""
quotes.py
=========
Easter-egg humor feature: `/smurf <agent>` replies with a random quote
ribbing that agent.

    /smurf carlo            → random Carlo quote
    /smurf jnj              → JNJ's quotes
    /smurf wistama          → Wistama's quotes (same pool as JNJ)
    /smurf                  → prompts with the list of known agents

Agent names and their quotes live in agent_quotes.txt:
    **Agent Name**
    1. quote text
    2. quote text

A header naming two agents who share quotes can be written with "&", "and",
or "/" (e.g. "**JNJ & Wistama**"). They are listed as separate agents but
both return the same quote pool.
"""

import os
import random
import re

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from topic_guard import topic_allowed

# Conversation state for the two-step "/smurf" → "which agent?" flow
ASK_AGENT = 0

_QUOTES_FILE = os.path.join(os.path.dirname(__file__), "agent_quotes.txt")

_HEADER_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_QUOTE_RE = re.compile(r"^\d+\.\s*(.+)$")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _norm(text: str) -> str:
    """Normalize a name into a lookup key: lowercase, alphanumerics only."""
    return _NON_ALNUM.sub("", text.lower())


def _split_agents(name: str) -> list[str]:
    """Split a header into individual agent names.

    "JNJ & Wistama" -> ["JNJ", "Wistama"];  "d138" -> ["d138"]
    """
    parts = re.split(r"\s*(?:&|/|\band\b)\s*", name, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def load_quotes(path: str = _QUOTES_FILE):
    """Parse the file into ({key: [quotes]}, {key: display}, [display names in order])."""
    quotes: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    order: list[str] = []
    current_keys: list[str] = []
    current_quotes: list[str] = []

    def flush():
        for key in current_keys:
            quotes.setdefault(key, []).extend(current_quotes)

    with open(path, encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            header = _HEADER_RE.match(stripped)
            if header:
                flush()
                name = header.group(1).strip()
                agents = _split_agents(name)
                current_keys = []
                current_quotes = []
                # Each named agent is listed separately and shares the pool.
                for agent in agents:
                    k = _norm(agent)
                    if not k:
                        continue
                    current_keys.append(k)
                    display[k] = agent
                    if agent not in order:
                        order.append(agent)
                # Convenience alias for the combined form (e.g. "jnjwistama"),
                # usable in lookups but not shown in the agent list.
                if len(agents) > 1:
                    joined = _norm(name)
                    if joined not in current_keys:
                        current_keys.append(joined)
                        display.setdefault(joined, name)
                continue
            quote = _QUOTE_RE.match(stripped)
            if quote:
                current_quotes.append(quote.group(1).strip())
            elif current_quotes:
                # wrapped continuation of the previous quote
                current_quotes[-1] += " " + stripped
    flush()
    return quotes, display, order


def build_quote_handler() -> ConversationHandler:
    quotes, display, order = load_quotes()
    agent_list = ", ".join(order)

    def _lookup(raw: str):
        """Return (display_name, quote) for a name, or None if unknown."""
        candidates = [_norm(raw)]
        words = raw.split()
        if words:
            candidates.append(_norm(words[0]))
        for key in candidates:
            pool = quotes.get(key)
            if pool:
                return display.get(key, key), random.choice(pool)
        return None

    async def _answer(message, raw: str):
        result = _lookup(raw)
        if result:
            name, quote = result
            await message.reply_text(f"🔷 {name}\n\n{quote}")
        else:
            await message.reply_text(
                f"Never heard of 'em. I know these blue mooks: {agent_list}."
            )

    # ENTRY — /smurf [agent]. With a name, answer now; without, ask for one.
    async def smurf(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not topic_allowed(update, context, "smurf"):
            return ConversationHandler.END
        raw = " ".join(context.args).strip()
        if not raw:
            await update.message.reply_text(
                "Who you askin' about? Send me a name.\n"
                f"I got dirt on: {agent_list}."
            )
            return ASK_AGENT
        await _answer(update.message, raw)
        return ConversationHandler.END

    # STEP — the agent name sent as a follow-up message
    async def receive_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _answer(update.message, update.message.text.strip())
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("smurf", smurf)],
        states={ASK_AGENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_agent)]},
        fallbacks=[],
        allow_reentry=True,
    )
