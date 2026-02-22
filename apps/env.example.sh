#!/usr/bin/env bash

# 1) Copy this file to apps/env.sh
# 2) Put your values below
# 3) Run: source apps/env.sh

export TELEGRAM_API_ID="PUT_YOUR_API_ID_HERE"
export TELEGRAM_API_HASH="PUT_YOUR_API_HASH_HERE"
export TELEGRAM_BOT_TOKEN="PUT_YOUR_BOT_TOKEN_HERE"

# Optional (only if you have 2FA enabled)
export TELEGRAM_PASSWORD="PUT_YOUR_2FA_PASSWORD_HERE"

# Optional (live bot lane helper peer, e.g. @telecraftorbotandi)
export TELECRAFT_LIVE_BOT_TEST_PEER="@your_group_or_channel"

# Optional (override bot session path for tests/live --live-bot)
export TELEGRAM_BOT_SESSION_PATH=""

