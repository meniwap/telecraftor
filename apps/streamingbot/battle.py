from __future__ import annotations

import hashlib
import random

_ARENAS = (
    "{left} נכנס לזירה עם ביטחון מוגזם, ו-{right} הגיע עם פרצוף של מי שכבר ראה production.",
    "בקרב בין {left} ל-{right}, הקהל דרש שקיפות ושני הצדדים שלפו מצגות.",
    "{left} פתח חזק, אבל {right} ביקש רגע לבדוק מה כתוב ב־README של האירוע.",
    "על הנייר {left} הוביל, בפועל {right} הביא יותר אנרגיה של יום חמישי בערב.",
)

_MOVES = (
    "{left} תקף עם טיעון מרשים, אבל {right} ענה בשקט עם 'זה עבד אצלי'.",
    "{right} ניסה מהלך טקטי, ו-{left} הגיב כאילו מישהו נגע לו בקובץ קונפיג.",
    "{left} שלח עקיצה מדויקת, אבל {right} חזר עם נתון שלא אומת ועדיין נשמע סמכותי.",
    "{right} עשה pivot מבריק, ו-{left} ביקש timeout כדי לעדכן את הנרטיב.",
)

_VERDICTS = (
    "בסוף השופטים נתנו נקודות לשניהם, כי היה קשה להוכיח מי מהם יותר מבולגן.",
    "הקהל הכריז על תיקו, בעיקר כי אף אחד לא רצה לפתוח incident חדש.",
    "ניצחון טכני נרשם, אבל לא ברור של מי; זה היה רגע קלאסי של ועדת היגוי.",
    "המסקנה הרשמית הייתה ש-{left} ו-{right} שניהם מסוכנים כשנותנים להם מיקרופון.",
)


def _make_rng(left: str, right: str, variant: int) -> random.Random:
    material = f"battle:{variant}:{left}|{right}".encode()
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest[:8], "big", signed=False))


def build_battle_lines(
    left: str,
    right: str,
    *,
    count: int = 8,
    variant: int = 0,
) -> list[str]:
    if count <= 0:
        return []
    left_name = str(left).strip() or "חתול"
    right_name = str(right).strip() or "כלב"
    rng = _make_rng(left_name, right_name, variant)
    lines: list[str] = []
    for idx in range(1, count + 1):
        if idx % 3 == 1:
            line = rng.choice(_ARENAS).format(left=left_name, right=right_name)
        elif idx % 3 == 2:
            line = rng.choice(_MOVES).format(left=left_name, right=right_name)
        else:
            line = rng.choice(_VERDICTS).format(left=left_name, right=right_name)
        lines.append(f"{idx}. {line}")
    return lines
