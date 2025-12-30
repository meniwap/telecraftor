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

- להקשיב ל־updates (תשלח לעצמך הודעה בזמן שזה רץ)

```bash
./.venv/bin/python apps/run.py updates --network prod --dc 2
```

