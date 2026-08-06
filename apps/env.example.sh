#!/usr/bin/env bash

# 1) Copy this file to apps/env.sh
# 2) Run: chmod 600 apps/env.sh
# 3) Put your values below without typing them in a shell command
# 4) Run: source apps/env.sh
# apps/env.sh is Git-ignored. Environment variables stay out of argv but can still be read by
# same-user processes, so prefer secret-manager injection where available.

export TELEGRAM_API_ID="PUT_YOUR_API_ID_HERE"
export TELEGRAM_API_HASH="PUT_YOUR_API_HASH_HERE"
export TELEGRAM_BOT_TOKEN="PUT_YOUR_BOT_TOKEN_HERE"

# Optional (only if you have 2FA enabled)
# Prefer leaving this unset and typing 2FA interactively.
# export TELEGRAM_PASSWORD=""

# Optional (live bot lane helper peer, e.g. @telecraftorbotandi)
export TELECRAFT_LIVE_BOT_TEST_PEER="@your_group_or_channel"

# Optional (override bot session path for manual bot checks)
export TELEGRAM_BOT_SESSION_PATH=""
