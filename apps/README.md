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

- Login בסנדבוקס (ברירת מחדל בטוחה; שומר session תחת `.sessions/sandbox/`)

```bash
./.venv/bin/python apps/run.py login --runtime sandbox --dc 2
```

- getMe

```bash
./.venv/bin/python apps/run.py me --runtime sandbox --dc 2
```

- לשלוח הודעה לעצמך (Saved Messages)

```bash
./.venv/bin/python apps/run.py send-self "hi" --runtime sandbox --dc 2
```

- לשלוח הודעה ל־peer דרך resolve (username/phone)

```bash
./.venv/bin/python apps/run.py send "@username" "hi from telecraft" --runtime sandbox
./.venv/bin/python apps/run.py send "+15551234567" "hi" --runtime sandbox
./.venv/bin/python apps/run.py send "channel:123456789" "hi" --runtime sandbox
```

- להקשיב ל־updates (תשלח לעצמך הודעה בזמן שזה רץ)

```bash
./.venv/bin/python apps/run.py updates --runtime sandbox --dc 2
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

#### Session / state קבצים (לא נכנסים לגיט)

בתיקייה `.sessions/` נוצרים:
- `.sessions/sandbox/test_dcX.session.json`: auth_key + endpoint/framing + server_salt
- `.sessions/sandbox/test_dcX.updates.json`: updates state מינימלי
- `.sessions/sandbox/test_dcX.entities.json`: entity cache מינימלי
- `.sessions/sandbox/current`: pointer לסשן הסנדבוקס
- `.sessions/prod/prod_dcX.*` ו-`.sessions/prod/current`: lane נפרד לפרוד
