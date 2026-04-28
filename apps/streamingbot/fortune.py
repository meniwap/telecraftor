from __future__ import annotations

import hashlib
import random

_FORECASTS = (
    "תיתקל בסימן מפתיע סביב {topic}, והוא ייראה חשוד אבל יהיה די שימושי.",
    "משהו בעניין {topic} יישמע היום מסוכן, אבל בעצם רק יבקש קפה ותשומת לב.",
    "היקום יזרוק עליך סביב {topic} משימה קטנה שתישמע גדולה רק במייל הראשון.",
    "בכל הקשור ל-{topic}, עדיף לענות לאט ובביטחון של מישהו שלא פתח עדיין את הלוגים.",
    "צפויה התקדמות קלה ב-{topic}, כל עוד לא תנסה להסביר אותה ביותר מדי שקופיות.",
)

_ADVICE = (
    "אם תהיה מבולבל, תנהג כאילו זו הייתה התוכנית המקורית.",
    "כדאי להנהן פעמיים לפני כל תשובה, זה מוסיף סמכות מיותרת אבל אפקטיבית.",
    "אל תתווכח עם ההשראה הראשונה, היא כנראה עברה QA פנימי בדרך.",
    "תן מקום גם לפתרון המצחיק, לפעמים הוא היחיד שמגיע בזמן.",
    "אחרי 16:00 מותר לך לקרוא לזה ניסוי במקום תקלה.",
)

_OUTCOMES = (
    "בסוף עוד יגידו שהיה לך חזון, למרות שכולנו יודעים שהיה לך בעיקר מזל.",
    "היום יסתיים טוב יותר אם תסכים לתת למציאות לקרוא לזה draft.",
    "בערב מישהו יספר שזה היה מהלך אסטרטגי, וכולם יחליטו לזרום איתו.",
    "לפני השינה תבין שהתחזית צדקה בעיקר בטון, פחות בפרטים.",
    "הכוכבים ממליצים לא למחוק כלום עד מחר בבוקר.",
)


def _make_rng(prompt: str, variant: int) -> random.Random:
    material = f"fortune:{variant}:{prompt}".encode()
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest[:8], "big", signed=False))


def build_fortune_lines(prompt: str, *, count: int = 8, variant: int = 0) -> list[str]:
    if count <= 0:
        return []
    topic = str(prompt).strip() or "היום שלך"
    rng = _make_rng(topic, variant)
    lines: list[str] = []
    for idx in range(1, count + 1):
        forecast = rng.choice(_FORECASTS).format(topic=topic)
        advice = rng.choice(_ADVICE)
        outcome = rng.choice(_OUTCOMES)
        lines.append(f"{idx}. {forecast} {advice} {outcome}")
    return lines
