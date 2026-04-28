from __future__ import annotations

import hashlib
import random

_OPENERS = (
    "בבוקר של {topic}, המעלית החליטה לדבר רק בסיסמאות sprint.",
    "בפינת {topic}, מכונת הקפה הכריזה על עצמה כראש צוות זמני.",
    "במרכז האירוע של {topic}, הלוח בחדר ישיבות התחיל לכתוב משימות לבד.",
    "באמצע {topic}, מישהו פתח מצגת והיא פתחה אותו בחזרה.",
    "ברגע הכי רגיש של {topic}, הסטטוס בישיבה הפך למסיבת עיתונאים.",
)

_MIDDLES = (
    "אף אחד לא נבהל, כי כולם היו בטוחים שזה חלק מהתהליך.",
    "המתמחה סימן הכול בירוק, למרות שהכול היה בצבע של חשש קל.",
    "מנהל המוצר הנהן כאילו זו הייתה הדרישה המקורית מהיום הראשון.",
    "ה־QA כתב באג חדש בשם: 'האווירה מתפקדת לאט'.",
    "מישהו לחש שזה נראה רע, ואז ביקש להפוך את זה ל־roadmap.",
)

_TWISTS = (
    "בסוף התברר שהבעיה נפתרה רק כי כולם הלכו לאכול.",
    "מאותו יום קראו לזה פיצ'ר, כי כבר לא היה נעים לחזור אחורה.",
    "האירוע נסגר רק אחרי שמישהו הציע לו KPI וכולם נרגעו.",
    "מאז כל מי ששומע על זה פשוט פותח עוד טאב ומעמיד פנים שזה בסדר.",
    "וככה נולד נוהל חדש: קודם נושמים, אחר כך עושים deploy.",
)


def _make_rng(prompt: str, variant: int) -> random.Random:
    material = f"story:{variant}:{prompt}".encode()
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest[:8], "big", signed=False))


def build_story_lines(prompt: str, *, count: int = 7, variant: int = 0) -> list[str]:
    if count <= 0:
        return []
    topic = str(prompt).strip() or "יום במשרד"
    rng = _make_rng(topic, variant)
    lines: list[str] = []
    for idx in range(1, count + 1):
        opener = rng.choice(_OPENERS).format(topic=topic)
        middle = rng.choice(_MIDDLES)
        twist = rng.choice(_TWISTS)
        lines.append(f"{idx}. {opener} {middle} {twist}")
    return lines
