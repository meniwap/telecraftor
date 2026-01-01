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

- Login (שומר קובץ session תחת `.sessions/`)

```bash
./.venv/bin/python apps/run.py login --network prod --dc 2
```

- getMe

```bash
./.venv/bin/python apps/run.py me --network prod --dc 2
```

- לשלוח הודעה לעצמך (Saved Messages)

```bash
./.venv/bin/python apps/run.py send-self "hi" --network prod --dc 2
```

- לשלוח הודעה ל־peer דרך resolve (username/phone)

```bash
./.venv/bin/python apps/run.py send "@username" "hi from telecraft" --network prod
./.venv/bin/python apps/run.py send "+15551234567" "hi" --network prod
./.venv/bin/python apps/run.py send "channel:123456789" "hi" --network prod
```

- להקשיב ל־updates (תשלח לעצמך הודעה בזמן שזה רץ)

```bash
./.venv/bin/python apps/run.py updates --network prod --dc 2
```

#### Echo bot (framework demo)

אחרי login:

```bash
./.venv/bin/python apps/echo_bot.py
```

מה אמור לקרות:
- בקבוצות “רגילות” (basic group) זה יחזיר echo לאותו צ’אט.
- ב־DM / ערוצים / סופרגרופ: זה יעבוד **אם** יש `access_hash` בזיכרון (ה־Dispatcher עושה priming דרך dialogs בתחילת ריצה).
- אם אין מספיק מידע כדי לבנות peer (למשל DM ממש “חדש” שלא הופיע ב־dialogs), יש fallback ל־Saved Messages.

#### Session / state קבצים (לא נכנסים לגיט)

בתיקייה `.sessions/` נוצרים:
- `prod_dcX.session.json`: auth_key + endpoint/framing + server_salt
- `prod_dcX.updates.json`: updates state מינימלי (pts/qts/seq/date) כדי שהבוט יחזיק ריסטארטים יותר טוב
- `prod_dcX.entities.json`: entity cache מינימלי (user/channel access_hash) כדי ש־reply ב־DM/ערוצים יעבוד גם אחרי ריסטארט
- `prod.current`: pointer לסשן “הנוכחי”

