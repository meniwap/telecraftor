from __future__ import annotations

import hashlib
import random

_SETUPS = (
    "שאלתי את הראוטר על החיים",
    "הבאג נכנס לישיבת צוות",
    "פתחתי לוגים באמצע הלילה",
    "המתכנת דיבר עם הדיפלוימנט",
    "המחשב ביקש קפה לפני הבוט",
    "הסקריפט ניסה להישמע בטוח בעצמו",
    "הדדליין נכנס לחדר באיטיות",
    "השרת עשה פרצוף של יום ראשון",
    "מחולל הבדיחות פגש QA חשדן",
    "הפונקציה נשבעה שהיא טהורה",
    "הקונפיג ראה אותי מתקרב",
    "הקומיט ביקש שלא אקרא לו 'זמני'",
)

_PUNCHES = (
    "ואמר: \"לפני תשובות, תעשה ריסטארט לנפש.\"",
    "ואז טען שהבעיה היא בכלל בצד של המציאות.",
    "ומאז כל ה־stack trace נשמע כמו סטנדאפ.",
    "אבל רק אחרי retry שלישי הוא הסכים לשתף פעולה.",
    "ומשם הכל הידרדר לשיחה על why it works on my machine.",
    "ומאז אני חושד שגם לקאש יש חוש הומור.",
    "ובסוף כולם מחאו כפיים ל־semicolon שלא נשבר.",
    "ואז שלח הודעת שגיאה עם ביטחון של מנהל מוצר.",
    "אבל בגדול הוא רק רצה עוד חמש דקות ב־maintenance mode.",
    "ומאז כל תשובה שלו נשמעת כמו patch note עייף.",
    "והוכיח ש־debugging זה בעצם טיפול זוגי לקוד.",
    "ואז כתב README שמסביר למה זו לא באמת תקלה.",
)

_TWISTS = (
    "אני לא אומר שזה מקצועי, אבל זה כן מאוד משכנע.",
    "בקיצור, גם למכונות יש רגעים של דרמה.",
    "זו לא בדיחה פרטית, זה פשוט log ברמת רגש.",
    "מאז אני בודק גם stack וגם מצב רוח.",
    "אף אחד לא הבין, אבל כולם הרגישו שזה production.",
    "אם זה לא פתרון, לפחות זה נשמע כמו אחד.",
    "ומשם התחלנו לקרוא לזה feature תודעתי.",
    "זה היה הרגע שהבנתי שגם תקלות רוצות תשומת לב.",
    "לא תיקנתי כלום, אבל האווירה נהייתה יציבה יותר.",
    "וככה נולדה עוד ישיבת postmortem עם חיוך עקום.",
)


def _make_rng(prompt: str, variant: int) -> random.Random:
    material = f"joke:{variant}:{str(prompt).strip()}".encode()
    digest = hashlib.sha256(material).digest()
    seed = int.from_bytes(digest[:8], "big", signed=False)
    return random.Random(seed)


def build_joke_lines(prompt: str, *, count: int = 10, variant: int = 0) -> list[str]:
    if count <= 0:
        return []
    topic = str(prompt).strip() or "הייטק"
    rng = _make_rng(topic, variant)
    lines: list[str] = []
    for idx in range(1, count + 1):
        setup = rng.choice(_SETUPS)
        punch = rng.choice(_PUNCHES)
        twist = rng.choice(_TWISTS)
        lines.append(f"{idx}. בנושא {topic}: {setup}, {punch} {twist}")
    return lines
