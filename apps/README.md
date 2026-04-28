### איך מריצים (פשוט)

#### פעם אחת: התקנה

מהרוט של הפרויקט:

```bash
cd /Users/meniwap/telecraftor
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
```

#### פעם אחת: לשים API ID/HASH בלי להכניס לקוד

```bash
cp apps/env.example.sh apps/env.sh
```

תפתח `apps/env.sh` ותשים שם את הערכים שלך (זה לא נכנס ל־git).

ואז:

```bash
source apps/env.sh
```

#### הרצה

- Login בפרוד (שומר session תחת `.sessions/prod/`)

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod --dc 2
```

- Login לבוט (MTProto bot account via token; שומר bot session נפרד)

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --dc 2
# או:
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --bot-token "$TELEGRAM_BOT_TOKEN"
```

- getMe

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --session-kind bot --dc 2
```

- לשלוח הודעה לעצמך (Saved Messages)

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send-self "hi" --runtime prod --allow-prod --dc 2
```

- לשלוח הודעה ל־peer דרך resolve (username/phone)

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send "@username" "hi from telecraft" --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send "+15551234567" "hi" --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send "channel:123456789" "hi" --runtime prod --allow-prod
```

- להקשיב ל־updates (תשלח לעצמך הודעה בזמן שזה רץ)

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py updates --runtime prod --allow-prod --dc 2
```

#### פרוד (רק אם אתה בטוח)

חסום כברירת מחדל ודורש גם flag וגם env:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --dc 2
```

#### Echo bot (framework demo)

אחרי login:

```bash
./.venv/bin/python apps/echo_bot.py
```

#### Command bot (demo: /ping, /send @username ...)

```bash
./.venv/bin/python apps/command_bot.py
```

הבוט הזה משתמש ב-`telecraft.bot.run_userbot()` כדי לקבל ריצה יציבה (reconnect/backoff).

מה אמור לקרות:
- בקבוצות “רגילות” (basic group) זה יחזיר echo לאותו צ’אט.
- ב־DM / ערוצים / סופרגרופ: זה יעבוד **אם** יש `access_hash` בזיכרון (ה־Dispatcher עושה priming דרך dialogs בתחילת ריצה).
- אם אין מספיק מידע כדי לבנות peer (למשל DM ממש “חדש” שלא הופיע ב־dialogs), יש fallback ל־Saved Messages.

#### MTProto bot keyboard demo (`אני חתול` + Yes/No)

אחרי `login-bot`:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/bot_keyboard_demo.py --runtime prod --allow-prod --target @meniwap
```

מה אמור לקרות:
- הבוט שולח הודעה: `אני חתול`
- יש כפתורי inline: `כן` / `לא`
- בלחיצה מתקבל callback query, הבוט מחזיר toast ומעדכן את ההודעה.

#### Streaming bot (Bot API draft streaming)

הדמו הזה לא משתמש ב־MTProto. הוא משתמש ב־Bot API הרשמי כי שם Telegram תיעדה את
`sendMessageDraft` ל־streaming של טקסט חלקי בצ'אט פרטי.

לפני הרצה:

```bash
source apps/env.sh
```

וודא שיש לך:

```bash
export TELEGRAM_STREAMING_BOT_TOKEN="123456:ABC..."
```

הרצה:

```bash
./.venv/bin/python -m apps.streamingbot.main
```

מה אמור לקרות:
- בפרטי: הבוט יגדיל draft בהדרגה ואז ישלח תשובה סופית לפי mode.
- יש פקודות כמו `/joke`, `/story`, `/battle`, `/fortune`, וגם `/menu` ו-`/stop`.
- יש גם reply keyboard ו-inline buttons ל-"עוד כזה", "ערבב" ומעבר מהיר בין מצבים.
- בקבוצה/ערוץ: הבוט יבקש לעבור לפרטי.

#### Group bot (plugin-based, לקבוצות אמיתיות)

אחרי `login-bot`:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py --runtime prod --allow-prod --config apps/bot_config.json
```

מה יש בפנים:
- פלאגינים נפרדים תחת `apps/bot_plugins/`
- Storage ב-SQLite (warnings/stats/modlog/schedules)
- middleware של scope (`allowed_peers`) ו-permissions
- מצב `read_only_mode` (dry-run) לפעולות מסוכנות

לפרטים מלאים + צ'קליסט בדיקות בקבוצה:
- `docs/16_group_bot_guide.md`

#### Session / state קבצים (לא נכנסים לגיט)

בתיקייה `.sessions/` נוצרים:
- `.sessions/prod/prod_dcX.session.json`: auth_key + endpoint/framing + server_salt
- `.sessions/prod/prod_dcX.bot.session.json`: bot auth session (נפרד מחשבון משתמש)
- `.sessions/prod/prod_dcX.updates.json`: updates state מינימלי
- `.sessions/prod/prod_dcX.entities.json`: entity cache מינימלי
- `.sessions/prod/current`: pointer לסשן משתמש בפרוד
- `.sessions/prod/current_bot`: pointer לסשן bot בפרוד
