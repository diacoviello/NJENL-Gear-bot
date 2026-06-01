# 🔷 Ingress Group Telegram Bot (Python)

A guided, button-driven Telegram bot for Ingress player coordination. Built with
`python-telegram-bot` v22 using native `ConversationHandler` flows — no fragile
state hacks.

## What it does

```
/need
  └─ Gear type buttons
       ├─ Resonators    → Level buttons → Location → SAVE
       ├─ Bursters      → Level buttons → Location → SAVE
       ├─ Ultra Strikes → Level buttons → Location → SAVE
       ├─ Cubes         → Level buttons → Location → SAVE
       ├─ Mods          → Mod buttons   → Location → SAVE
       └─ Other         → Free text     → Location → SAVE

/need near Paramus           → button flow, location pre-filled (skips final prompt)
/need L8 XMPs                → skips to location prompt
/need L8 XMPs near Paramus   → saves immediately

/have    → identical flow, stored as an OFFER
```

### Command summary

| Command | What it does |
|---|---|
| `/need` | Request gear (guided buttons) |
| `/have` | Offer gear (guided buttons) |
| `/needs [location]` | List open requests, optional location filter |
| `/offers [location]` | List available offers |
| `/filled <id>` | Close your own request |
| `/cancel <id>` | Withdraw your own offer |
| `/help` | Show all commands |

---

## Project structure

```
python-bot/
├── bot.py            # Entry point — wires up all flows from config
├── topics.py         # ★ Declarative flow + button definitions (edit this to add topics)
├── conversation.py   # Builds ConversationHandler for /need, /have
├── lookups.py        # Builds /needs, /offers, /filled, /cancel
├── storage.py        # SQLite key/value storage
└── requirements.txt
```

---

## Run locally

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_token_from_botfather"
python bot.py
```

Or create a `.env` file:
```
BOT_TOKEN=your_token_from_botfather
```

---

## Deploy to free hosting

### Option 1 — Railway.app (easiest, recommended)

1. Push this folder to a GitHub repo.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repo.
4. Under **Variables**, add: `BOT_TOKEN` = your token.
5. Railway auto-detects Python. Set the **Start Command** to:
   ```
   python bot.py
   ```
6. Deploy. The bot runs 24/7.

> The included `Procfile` tells Railway/Render how to start the bot automatically.

### Option 2 — Render.com

1. Push to GitHub.
2. [render.com](https://render.com) → **New** → **Background Worker**.
3. Connect your repo.
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `python bot.py`
6. Add environment variable `BOT_TOKEN`.
7. Create. (Note: Render's free tier may sleep; a Background Worker is best for bots.)

### Option 3 — PythonAnywhere

1. Upload the folder (or clone from GitHub) in a Bash console.
2. `pip install --user -r requirements.txt`
3. Set the token: `export BOT_TOKEN=...` (or hardcode in a `.env`).
4. Run in an **Always-on task**: `python3 bot.py`

### Option 4 — Any VPS (Hetzner, DigitalOcean, Oracle Free Tier)

Use the included `ingressbot.service` systemd unit:
```bash
sudo cp ingressbot.service /etc/systemd/system/
sudo systemctl enable --now ingressbot
```

---

## Group setup

1. Add the bot to your Telegram group.
2. In **BotFather**, run `/setprivacy` → **Disable** so the bot can read group commands.
3. Make the bot an admin (so it can read all messages).
4. Members use `/need`, `/have`, etc. in the group.

> Note: inline keyboard buttons work in group chats. Each user's flow is tracked
> per-user, so multiple agents can run `/need` at the same time without collisions.

---

## Adding a new topic

Open `topics.py` and copy the commented `mission` block in `FLOWS`. Fill in:
- `command` — the slash command (e.g. `mission`)
- `store_key` / `id_key` — unique storage bucket names
- `list_command`, `close_cmd`, labels, emoji

Save and restart. `bot.py` auto-builds the conversation, list, and close
commands for it — no other files need editing.

> The button steps (gear type → level/mod/other → location) are shared. If your
> new topic needs *different* buttons, edit the option lists at the top of
> `topics.py` or add new states in `conversation.py`.
