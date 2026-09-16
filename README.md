# Zynex Cartel — Telegram Giveaway Bot

A production-ready Telegram bot for managing giveaways with three types: Vote, Random, and Slot.

## Features

- **Vote Giveaway** — Users vote for their favorite participant
- **Random Giveaway** — Cryptographically secure random winner selection  
- **Slot Giveaway** — Match triple-7 to win
- **Scheduled Giveaways** — Auto-start and auto-end
- **Admin Controls** — Manual winner selection, ban/unban, sudo users
- **Mandatory Channels** — Users must join channels before participating

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env` with your bot token and settings
4. Run: `python zynex_cartel/main.py`

## Deployment

Deploy to Railway or any Python hosting platform. The `Procfile` and `railway.json` are pre-configured.

## Environment Variables

See `zynex_cartel/.env.example` for all configuration options.
