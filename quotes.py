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
from telegram.ext import CommandHandler, ContextTypes

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


def build_quote_handler() -> CommandHandler:
    quotes, display, order = load_quotes()
    agent_list = ", ".join(order)

    async def smurf(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Who you askin' about? Gimme a name.\n"
                f"I got dirt on: {agent_list}.\n"
                "Like this: /smurf carlo"
            )
            return

        # Try the full argument string first (for multi-word names), then
        # fall back to just the first word.
        candidates = [_norm(" ".join(context.args)), _norm(context.args[0])]
        for key in candidates:
            pool = quotes.get(key)
            if pool:
                await update.message.reply_text(
                    f"🔷 {display.get(key, key)}\n\n{random.choice(pool)}"
                )
                return

        await update.message.reply_text(
            f"Never heard of 'em. I know these blue mooks: {agent_list}."
        )

    return CommandHandler("smurf", smurf)
