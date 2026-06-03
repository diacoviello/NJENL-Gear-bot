"""
transport.py
============
Gear transport chain: coordinate a multi-hop delivery between agents.

  Scenario:
    agent1 needs L8 XMPs in Paramus (open /need)
    agent3 has L8 XMPs in Long Branch (available /have)
    agent2 volunteers to run the gear between them

  Commands:
    /run <need_id> <offer_id>   — volunteer as the runner
    /runs                       — list your active runs
    /delivered <run_id>         — mark a run as delivered (runner or recipient)

  On /run, the bot:
    1. Validates both the need and the offer are still open.
    2. Creates a transport record.
    3. Posts the chain summary in the chat.
    4. DMs the requester and provider to let them know (best-effort; silently skips
       if the user hasn't started the bot privately).

  On /delivered, the bot closes the transport record and marks the underlying
  need (#filled) and offer (#cancelled) automatically.
"""

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from topic_guard import topic_allowed


def _uname(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


async def _try_dm(bot, user_id: int, text: str, **kwargs):
    """Send a DM; silently swallow errors if the user hasn't started the bot."""
    try:
        await bot.send_message(user_id, text, **kwargs)
    except Exception:
        pass


# ── /run <need_id> <offer_id> ────────────────────────────────────────────────────

async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "run"):
        return
    storage = context.bot_data["storage"]

    if len(context.args) != 2 or not all(a.isdigit() for a in context.args):
        await update.message.reply_text(
            "Gimme the need ID and the offer ID.\n`/run <need_id> <offer_id>`",
            parse_mode="Markdown",
        )
        return

    need_id  = int(context.args[0])
    offer_id = int(context.args[1])

    needs  = storage.list("gear_requests")
    offers = storage.list("gear_offers")

    need  = next((e for e in needs  if e["id"] == need_id  and e["status"] == "open"),      None)
    offer = next((e for e in offers if e["id"] == offer_id and e["status"] == "available"), None)

    if not need:
        await update.message.reply_text(
            f"Need #{need_id} doesn't exist or is already handled. Check `/needs`.",
            parse_mode="Markdown",
        )
        return
    if not offer:
        await update.message.reply_text(
            f"Offer #{offer_id} doesn't exist or is already handled. Check `/offers`.",
            parse_mode="Markdown",
        )
        return

    runner          = update.effective_user
    runner_username = _uname(runner)

    run_id = storage.next_id("transport_next_id")
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

    # Chat announcement
    await update.message.reply_text(
        f"🚗 *Transport Chain — Run #{run_id}*\n\n"
        f"📦 *Gear:* {offer['items']}\n"
        f"🎁 *Provider:* {offer['username']}  _(at {offer['location']})_\n"
        f"🚗 *Runner:* {runner_username}\n"
        f"📍 *Recipient:* {need['username']}  _(at {need['location']})_\n\n"
        f"When the gear's in hand, hit `/delivered {run_id}`.",
        parse_mode="Markdown",
    )

    # DM the requester
    await _try_dm(
        context.bot,
        need["user_id"],
        f"🚗 *Good news* — {runner_username} is running your gear.\n\n"
        f"📦 {offer['items']} from {offer['username']} ({offer['location']}) "
        f"is on its way to you.\nRun ID: #{run_id}",
        parse_mode="Markdown",
    )

    # DM the provider
    await _try_dm(
        context.bot,
        offer["user_id"],
        f"🚗 *Heads up* — {runner_username} is picking up your gear.\n\n"
        f"📦 {offer['items']} → going to {need['username']} at {need['location']}.\n"
        f"Run ID: #{run_id}",
        parse_mode="Markdown",
    )


# ── /runs ────────────────────────────────────────────────────────────────────────

async def runs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "runs"):
        return
    storage = context.bot_data["storage"]
    user_id = update.effective_user.id

    active = [
        r for r in storage.list("transport_runs")
        if r["runner_id"] == user_id and r["status"] == "active"
    ]

    if not active:
        await update.message.reply_text(
            "You got no active runs. Step up with `/run <need_id> <offer_id>`.",
            parse_mode="Markdown",
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


# ── /delivered <run_id> ──────────────────────────────────────────────────────────

async def delivered_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not topic_allowed(update, context, "delivered"):
        return
    storage = context.bot_data["storage"]
    user_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Which run? `/delivered <run_id>`", parse_mode="Markdown"
        )
        return

    run_id = int(context.args[0])
    runs   = storage.list("transport_runs")
    run    = next((r for r in runs if r["id"] == run_id), None)

    if not run:
        await update.message.reply_text(f"Run #{run_id}? Never heard of it.")
        return
    if run["status"] != "active":
        await update.message.reply_text(
            f"Run #{run_id} is already {run['status']}. Nothing to do."
        )
        return
    if user_id not in (run["runner_id"], run["requester_id"]):
        await update.message.reply_text(
            "⚠️ That ain't your run to close out. Only the runner or the recipient can mark it done."
        )
        return

    # Mark the run
    run["status"] = "delivered"
    storage.set("transport_runs", runs)

    # Close the underlying need and offer
    storage.update_status("gear_requests", run["need_id"],  "filled")
    storage.update_status("gear_offers",   run["offer_id"], "cancelled")

    await update.message.reply_text(
        f"✅ *Run #{run_id} — delivered.* The gear made it. That's how you do business.\n\n"
        f"Need #{run['need_id']} marked filled. Offer #{run['offer_id']} closed.",
        parse_mode="Markdown",
    )

    # Notify everyone else on the chain
    notify = (
        f"✅ Run #{run_id} is done. {run['items']} delivered: "
        f"{run['provider_username']} → {run['runner_username']} → {run['requester_username']}."
    )
    for uid in {run["runner_id"], run["requester_id"], run["provider_id"]} - {user_id}:
        await _try_dm(context.bot, uid, notify)


# ── Handler list ─────────────────────────────────────────────────────────────────

def build_transport_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("run",       run_cmd),
        CommandHandler("runs",      runs_cmd),
        CommandHandler("delivered", delivered_cmd),
    ]
