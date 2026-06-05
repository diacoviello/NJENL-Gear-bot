"""
transport.py
============
Gear transport chain: coordinate a multi-hop delivery between agents.

  /run [need_id offer_id]   — volunteer as the runner (asks if omitted)
  /runs                     — list your active runs
  /delivered [run_id]       — mark a run done (asks if omitted)
"""

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from topic_guard import topic_allowed

_ASK_RUN_IDS  = 0
_ASK_DELIV_ID = 0  # separate ConversationHandlers, same int is fine


def _uname(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


async def _try_dm(bot, user_id: int, text: str, **kwargs):
    try:
        await bot.send_message(user_id, text, **kwargs)
    except Exception:
        pass


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fuhgeddaboudit.")
    return ConversationHandler.END


# ── /run ─────────────────────────────────────────────────────────────────────────

async def _do_run(update: Update, context: ContextTypes.DEFAULT_TYPE, need_id: int, offer_id: int):
    storage = context.bot_data["storage"]
    need  = next((e for e in storage.list("gear_requests") if e["id"] == need_id  and e["status"] == "open"),      None)
    offer = next((e for e in storage.list("gear_offers")   if e["id"] == offer_id and e["status"] == "available"), None)
    if not need:
        await update.message.reply_text(f"Need #{need_id} doesn't exist or is already handled.")
        return
    if not offer:
        await update.message.reply_text(f"Offer #{offer_id} doesn't exist or is already handled.")
        return
    runner          = update.effective_user
    runner_username = _uname(runner)
    run_id          = storage.next_id("transport_next_id")
    run = {
        "id":                 run_id,
        "need_id":            need_id,
        "offer_id":           offer_id,
        "runner_id":          runner.id,
        "runner_username":    runner_username,
        "requester_id":       need["user_id"],
        "requester_username": need["username"],
        "provider_id":        offer["user_id"],
        "provider_username":  offer["username"],
        "items":              offer["items"],
        "from_location":      offer["location"],
        "to_location":        need["location"],
        "status":             "active",
        "chat_id":            update.effective_chat.id,
        "created":            datetime.now(timezone.utc).isoformat(),
    }
    storage.append("transport_runs", run)
    await update.message.reply_text(
        f"🚗 *Transport Chain — Run #{run_id}*\n\n"
        f"📦 *Gear:* {offer['items']}\n"
        f"🎁 *Provider:* {offer['username']}  _(at {offer['location']})_\n"
        f"🚗 *Runner:* {runner_username}\n"
        f"📍 *Recipient:* {need['username']}  _(at {need['location']})_\n\n"
        f"When the gear's in hand, hit `/delivered {run_id}`.",
        parse_mode="Markdown",
    )
    await _try_dm(
        context.bot, need["user_id"],
        f"🚗 *Good news* — {runner_username} is running your gear.\n\n"
        f"📦 {offer['items']} from {offer['username']} ({offer['location']}) is on its way.\n"
        f"Run ID: #{run_id}",
        parse_mode="Markdown",
    )
    await _try_dm(
        context.bot, offer["user_id"],
        f"🚗 *Heads up* — {runner_username} is picking up your gear.\n\n"
        f"📦 {offer['items']} going to {need['username']} at {need['location']}.\n"
        f"Run ID: #{run_id}",
        parse_mode="Markdown",
    )


def build_run_handler() -> ConversationHandler:
    async def run_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not topic_allowed(update, context, "run"):
            return ConversationHandler.END
        if len(context.args) == 2 and all(a.isdigit() for a in context.args):
            await _do_run(update, context, int(context.args[0]), int(context.args[1]))
            return ConversationHandler.END
        await update.message.reply_text(
            "Which need, which offer? Send me both IDs with a space between 'em.\n"
            "_(e.g. `5 3` — need #5, offer #3)_\n\n"
            "Check `/needs` and `/offers` if you don't got the numbers.",
            parse_mode="Markdown",
        )
        return _ASK_RUN_IDS

    async def run_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
        parts = update.message.text.strip().split()
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            await update.message.reply_text(
                "Two numbers. Space between 'em. That's all I'm askin'. Or /cancel."
            )
            return _ASK_RUN_IDS
        await _do_run(update, context, int(parts[0]), int(parts[1]))
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("run", run_entry)],
        states={_ASK_RUN_IDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, run_receive)]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )


# ── /runs ─────────────────────────────────────────────────────────────────────────

async def runs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "runs"):
        return
    storage = context.bot_data["storage"]
    user_id = update.effective_user.id
    active = [r for r in storage.list("transport_runs") if r["runner_id"] == user_id and r["status"] == "active"]
    if not active:
        await update.message.reply_text(
            "You got no active runs. Step up with `/run <need_id> <offer_id>`.", parse_mode="Markdown"
        )
        return
    lines = ["🚗 *Your Active Runs:*\n"]
    for r in active:
        lines.append(
            f"*Run #{r['id']}*\n"
            f"  📦 {r['items']}\n"
            f"  🎁 From: {r['provider_username']}  ({r['from_location']})\n"
            f"  📍 To:   {r['requester_username']}  ({r['to_location']})\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /delivered ────────────────────────────────────────────────────────────────────

async def _do_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE, run_id: int):
    storage = context.bot_data["storage"]
    user_id = update.effective_user.id
    runs    = storage.list("transport_runs")
    run     = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        await update.message.reply_text(f"Run #{run_id}? Never heard of it.")
        return
    if run["status"] != "active":
        await update.message.reply_text(f"Run #{run_id} is already {run['status']}. Nothing to do.")
        return
    if user_id not in (run["runner_id"], run["requester_id"]):
        await update.message.reply_text("⚠️ That ain't your run to close out.")
        return
    run["status"] = "delivered"
    storage.set("transport_runs", runs)
    storage.update_status("gear_requests", run["need_id"],  "filled")
    storage.update_status("gear_offers",   run["offer_id"], "cancelled")
    await update.message.reply_text(
        f"✅ *Run #{run_id} — delivered.* The gear made it. That's how you do business.\n\n"
        f"Need #{run['need_id']} marked filled. Offer #{run['offer_id']} closed.",
        parse_mode="Markdown",
    )
    notify = (
        f"✅ Run #{run_id} is done. {run['items']} delivered: "
        f"{run['provider_username']} → {run['runner_username']} → {run['requester_username']}."
    )
    for uid in {run["runner_id"], run["requester_id"], run["provider_id"]} - {user_id}:
        await _try_dm(context.bot, uid, notify)


def build_delivered_handler() -> ConversationHandler:
    async def delivered_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not topic_allowed(update, context, "delivered"):
            return ConversationHandler.END
        if context.args and context.args[0].isdigit():
            await _do_delivered(update, context, int(context.args[0]))
            return ConversationHandler.END
        await update.message.reply_text(
            "Which run we closin' out? Send me the ID.\n_(Check `/runs` if you forgot the number.)_",
            parse_mode="Markdown",
        )
        return _ASK_DELIV_ID

    async def delivered_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("That ain't a number. You pullin' my leg? Try again or /cancel.")
            return _ASK_DELIV_ID
        await _do_delivered(update, context, int(text))
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("delivered", delivered_entry)],
        states={_ASK_DELIV_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivered_receive)]},
        fallbacks=[CommandHandler("cancel", _cancel)],
        allow_reentry=True,
    )


def build_transport_handlers() -> list:
    return [
        build_run_handler(),
        CommandHandler("runs", runs_cmd),
        build_delivered_handler(),
    ]
