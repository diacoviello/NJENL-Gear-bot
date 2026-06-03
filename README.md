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
       ├─ Cubes         → Level buttons (L1–L8, Hypercube) → Location → SAVE
       ├─ Mods          → Mod buttons   → Location → SAVE
       └─ Other         → Free text     → Location → SAVE

/need near Fairfield           → button flow, location pre-filled (skips final prompt)
/need L8 XMPs                → skips to location prompt
/need L8 XMPs near Red Bank   → saves immediately

/have    → identical flow, stored as an OFFER
```

### Command summary

#### Gear coordination

| Command                        | What it does                                          |
|-------------------------------|-------------------------------------------------------|
| `/need`                        | Request gear (guided buttons or one-liner)            |
| `/have`                        | Offer gear (guided buttons or one-liner)              |
| `/needs [location]`            | List open requests, optional location filter          |
| `/offers [location]`           | List available offers, optional location filter       |
| `/filled <id>`                 | Mark one of your requests as filled                   |
| `/cancel <id>`                 | Withdraw one of your offers                           |
| `/clearneeds`                  | Mark **all** your open requests as filled             |
| `/clearoffers`                 | Withdraw **all** your open offers                     |

#### Gear transport chain

| Command                        | What it does                                          |
|-------------------------------|-------------------------------------------------------|
| `/run <need_id> <offer_id>`    | Volunteer to run gear between two agents              |
| `/runs`                        | List your active transport runs                       |
| `/delivered <run_id>`          | Mark a run as delivered (closes the need + offer too) |

#### Family ranks

| Command    | What it does                                                    |
|------------|-----------------------------------------------------------------|
| `/rank`    | Check your rank (Underboss / Capo / Soldier / Associate)        |
| `/promote` | Promote someone to Soldier — reply to their message to use it   |
| `/family`  | See the full Family roster                                      |

#### Rat system

| Command            | What it does                        |
|--------------------|-------------------------------------|
| `/rat @username`   | Put someone on the rat list         |
| `/unrat @username` | Clear their name                    |
| `/rats`            | See who's currently on the list     |

#### Sopranos quote drops

| Command                  | What it does                                        |
|--------------------------|-----------------------------------------------------|
| `/tony @username`        | Tony's got a message for someone                    |
| `/paulie @username`      | Paulie weighs in                                    |
| `/christopher @username` | Christopher has feelings about this                 |
| `/silvio @username`      | Silvio's not pleased                                |
| `/junior @username`      | Junior knows better                                 |
| `/bobby @username`       | Bobby says a prayer for ya                          |
| `/carmela @username`     | Carmela's disappointed                              |
| `/smurf [agent]`         | Roast a blue agent by name                          |

> Omit `@username` on any Sopranos command for an undirected quote drop.

#### Topic management (Capo / Underboss only)

| Command                          | What it does                                                              |
|----------------------------------|---------------------------------------------------------------------------|
| `/settopic cmd1 cmd2 ...`        | Assign commands to the topic you run it from                              |
| `/settopic clear cmd1 cmd2 ...`  | Block commands everywhere, overriding built-in defaults                   |
| `/settopic list`                 | Show all effective topic assignments for this chat (anyone can run this)  |
| `/removetopic cmd1 cmd2 ...`     | Remove per-chat overrides — reverts to built-in defaults or stays blocked |

> Built-in defaults (defined in `topics.py → TOPIC_DEFAULTS`) are applied automatically.
> Per-chat overrides set via `/settopic` take precedence and persist across restarts.

---

## Project structure

```
python-bot/
├── bot.py                # Entry point — wires up all handlers and the job queue
├── topics.py             # ★ Flow definitions, gear options, and TOPIC_DEFAULTS
├── conversation.py       # ConversationHandler for /need and /have
├── lookups.py            # /needs, /offers, /filled, /cancel, /clearneeds, /clearoffers
├── transport.py          # /run, /runs, /delivered — gear transport chain
├── social.py             # /rat, /unrat, /rats, /rank, /promote, /family
├── sopranos.py           # /tony, /paulie, /christopher, /silvio, /junior, /bobby, /carmela
├── quotes.py             # /smurf — roast blue agents
├── topic_guard.py        # topic_allowed() guard + /settopic + /removetopic
├── matching.py           # DM users when a gear offer/need matches their open entry
├── expiry.py             # Background job: silently expire entries older than 7 days
├── storage.py            # SQLite key/value storage layer
├── agent_quotes.txt      # Quote data for /smurf
├── sopranos_quotes.txt   # Quote data for character drop commands
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

1. Push this folder to a GitHub repo (private is fine).
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repo.
4. Under **Variables**, add: `BOT_TOKEN` = your token.
5. Deploy. The included `railway.toml` already sets the build (Nixpacks),
   the start command (`python bot.py`), and a restart-on-crash policy — so
   there's nothing else to configure. The bot runs 24/7.

> **Replicas:** keep this at **1**. Two instances would both poll Telegram and
> trigger `Conflict: terminated by other getUpdates` errors.

### Option 2 — Render.com

The included `render.yaml` is a Blueprint that defines a background worker.

1. Push to GitHub.
2. [render.com](https://render.com) → **New** → **Blueprint** → connect your repo.
3. Render reads `render.yaml`, then prompts you to enter the `BOT_TOKEN` value
   (it's declared `sync: false`, so the secret never lives in the repo).
4. Create. (Note: background **workers** require a paid plan on Render; the free
   tier only covers web services, which sleep — bad for a polling bot.)

### Option 3 — PythonAnywhere

1. Upload the folder (or clone from GitHub) in a Bash console.
2. `pip install --user -r requirements.txt`
3. Set the token: `export BOT_TOKEN=...` (or hardcode in a `.env`).
4. Run in an **Always-on task**: `python3 bot.py`

### Option 4 — Any VPS (Hetzner, DigitalOcean, Oracle Free Tier)

Use the included `ingressbot.service` systemd unit. It reads the token from a
`.env` file via `EnvironmentFile`, so no secret is hardcoded in the unit:
```bash
sudo cp ingressbot.service /etc/systemd/system/
sudo systemctl enable --now ingressbot
```

### Deployment config files

| File | Used by | Purpose |
|---|---|---|
| `railway.toml` | Railway | Build + start command + restart policy |
| `render.yaml` | Render | Blueprint defining the worker + `BOT_TOKEN` |
| `Procfile` | Heroku / fallback | `worker: python bot.py` |
| `ingressbot.service` | systemd / VPS | Long-running service unit |

When a platform-specific file is present (e.g. `railway.toml`), it takes
precedence over the generic `Procfile`.

> ⚠️ **Data persistence:** the bot stores entries in a local SQLite file
> (`ingress_bot.db`). On Railway/Render the container filesystem is **ephemeral** —
> it is wiped on every redeploy and restart. To keep data, attach a persistent
> volume (e.g. mount `/data`) and point the DB at it. `Storage` accepts a path,
> so reading it from an env var (`DB_PATH`) lets you use `/data/ingress_bot.db`
> in production while keeping the default locally.

---

## Group setup

1. Add the bot to your Telegram group.
2. In **BotFather**, run `/setprivacy` → **Disable** so the bot can read group commands.
3. Make the bot an admin (so it can read all messages).
4. Members use `/need`, `/have`, etc. in the group.

> Note: inline keyboard buttons work in group chats. Each user's flow is tracked
> per-user, so multiple agents can run `/need` at the same time without collisions.

### Command menu (autocomplete)

To populate the `/` autocomplete menu, message **BotFather** → `/setcommands` →
select your bot → paste:

```
need - Guided: post something you need
have - Guided: post something you offer
needs - View open requests by location
offers - View available offers by location
filled - Close one of your requests (by id)
cancel - Withdraw one of your offers (by id)
clearneeds - Clear ALL your open requests
clearoffers - Clear ALL your open offers
help - Show all commands
```

---

## Adding a new topic

Open `topics.py` and copy the commented `mission` block in `FLOWS`. Fill in:
- `command` — the slash command (e.g. `mission`)
- `store_key` / `id_key` — unique storage bucket names
- `list_command`, `close_cmd`, `clear_cmd`, labels, emoji

Save and restart. `bot.py` auto-builds the conversation, list, and close
commands for it — no other files need editing.

> The button steps (gear type → level/mod/other → location) are shared. If your
> new topic needs *different* buttons, edit the option lists at the top of
> `topics.py` or add new states in `conversation.py`.
#   N J E N L - G e a r - b o t 
 
 