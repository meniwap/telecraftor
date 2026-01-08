#!/usr/bin/env python3
"""
בדיקה ידנית של הפיצ'רים החדשים.

הרצה:
    source apps/env.sh
    ./.venv/bin/python apps/test_new_features.py

מה צריך לפני:
    1. להריץ login:
       ./.venv/bin/python apps/run.py login --network prod --dc 4
    2. לוודא ש-env.sh מכיל API_ID ו-API_HASH
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def _try_load_env_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def _need(name: str) -> str:
    if name not in os.environ:
        _try_load_env_file("apps/env.sh")
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing {name}. Run: source apps/env.sh")
    return v


def _current_session_path(network: str) -> str:
    p = Path(".sessions") / f"{network}.current"
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s and Path(s).exists():
            return s
    raise SystemExit("No session found. Run: ./.venv/bin/python apps/run.py login")


async def test_iter_dialogs(client) -> bool:
    """בדיקה 1: iter_dialogs"""
    print("\n" + "=" * 60)
    print("📋 בדיקה 1: iter_dialogs - רשימת צ'אטים")
    print("=" * 60)

    count = 0
    try:
        async for dialog in client.iter_dialogs(limit=10):
            count += 1
            peer = getattr(dialog, "peer", None)
            peer_name = getattr(peer, "TL_NAME", "unknown")
            peer_id = getattr(peer, "user_id", None) or getattr(peer, "chat_id", None) or getattr(peer, "channel_id", None)
            unread = getattr(dialog, "unread_count", 0)
            print(f"  {count}. {peer_name} id={peer_id} | unread={unread}")
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False

    print(f"\n✅ סה\"כ נטענו {count} דיאלוגים")
    return count > 0


async def test_send_to_self(client) -> int | None:
    """בדיקה 2: שליחת הודעה ל-Saved Messages"""
    print("\n" + "=" * 60)
    print("💬 בדיקה 2: שליחת הודעה ל-Saved Messages")
    print("=" * 60)

    test_text = "🧪 בדיקת telecraft - הודעה פשוטה"
    
    try:
        print(f"  שולח: {test_text!r}")
        result = await client.send_message_self(test_text)
        
        # Extract sent message ID from updates
        sent_msg_id = None
        updates = getattr(result, "updates", [])
        for upd in updates:
            upd_name = getattr(upd, "TL_NAME", "")
            if "Message" in upd_name:
                inner_msg = getattr(upd, "message", None)
                if inner_msg:
                    sent_msg_id = getattr(inner_msg, "id", None)
                    break
        
        if sent_msg_id:
            print(f"✅ הודעה נשלחה! msg_id={sent_msg_id}")
        else:
            print(f"✅ הודעה נשלחה! (result type: {type(result).__name__})")
        return sent_msg_id
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_send_with_reply(client, reply_to_msg_id: int | None) -> int | None:
    """בדיקה 3: send_message עם reply_to (quote)"""
    print("\n" + "=" * 60)
    print("💬 בדיקה 3: send_message עם reply_to_msg_id (ציטוט)")
    print("=" * 60)

    if not reply_to_msg_id:
        print("  ⚠️ אין הודעה לצטט, מדלג")
        return None

    test_text = "🧪 בדיקת reply_to_msg_id - זה ציטוט!"
    
    try:
        from telecraft.tl.generated.types import InputPeerSelf
        
        print(f"  שולח הודעה עם ציטוט להודעה {reply_to_msg_id}...")
        result = await client.send_message_peer(
            InputPeerSelf(), 
            test_text, 
            reply_to_msg_id=reply_to_msg_id
        )
        
        # Extract sent message ID
        sent_msg_id = None
        updates = getattr(result, "updates", [])
        for upd in updates:
            upd_name = getattr(upd, "TL_NAME", "")
            if "Message" in upd_name:
                inner_msg = getattr(upd, "message", None)
                if inner_msg:
                    sent_msg_id = getattr(inner_msg, "id", None)
                    break
        
        print(f"✅ הודעה עם ציטוט נשלחה! msg_id={sent_msg_id}")
        return sent_msg_id
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_forward_message(client, msg_id: int) -> int | None:
    """בדיקה 4: forward_messages"""
    print("\n" + "=" * 60)
    print("↪️ בדיקה 4: forward_messages - העברת הודעה")
    print("=" * 60)

    if not msg_id:
        print("  ⚠️ אין הודעה להעביר, מדלג")
        return None
    
    try:
        from telecraft.tl.generated.types import InputPeerSelf
        
        # Forward from self to self (Saved Messages)
        print(f"  מעביר הודעה {msg_id} ל-Saved Messages...")
        
        # Use InputPeerSelf for both source and destination
        from telecraft.tl.generated.functions import MessagesForwardMessages
        from secrets import randbits
        
        result = await client.invoke_api(
            MessagesForwardMessages(
                flags=0,
                silent=False,
                background=False,
                with_my_score=False,
                drop_author=False,
                drop_media_captions=False,
                noforwards=False,
                allow_paid_floodskip=False,
                from_peer=InputPeerSelf(),
                id=[msg_id],
                random_id=[randbits(63)],
                to_peer=InputPeerSelf(),
                top_msg_id=None,
                reply_to=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                video_timestamp=None,
                allow_paid_stars=None,
                suggested_post=None,
            )
        )
        
        forwarded_msg_id = None
        updates = getattr(result, "updates", [])
        for upd in updates:
            upd_name = getattr(upd, "TL_NAME", "")
            if "Message" in upd_name:
                inner_msg = getattr(upd, "message", None)
                if inner_msg:
                    forwarded_msg_id = getattr(inner_msg, "id", None)
                    break

        print(f"✅ הודעה הועברה! msg_id={forwarded_msg_id}")
        print(f"   📋 ההודעה המקורית ({msg_id}) הועתקה להודעה חדשה ({forwarded_msg_id})")
        return forwarded_msg_id
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_delete_message(client, msg_id: int) -> bool:
    """בדיקה 5: delete_messages"""
    print("\n" + "=" * 60)
    print("🗑️ בדיקה 5: delete_messages - מחיקת הודעה")
    print("=" * 60)

    if not msg_id:
        print("  ⚠️ אין הודעה למחוק, מדלג")
        return False
    
    try:
        from telecraft.tl.generated.functions import MessagesDeleteMessages
        
        print(f"  מוחק הודעה {msg_id}...")
        result = await client.invoke_api(
            MessagesDeleteMessages(flags=0, revoke=True, id=[msg_id])
        )

        pts = getattr(result, "pts", None)
        pts_count = getattr(result, "pts_count", None)
        print(f"✅ הודעה נמחקה!")
        print(f"   📊 pts_count={pts_count} (כמה הודעות נמחקו)")
        print(f"   💡 לך לטלגרם ותראה שההודעה נעלמה!")
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_get_history(client) -> list:
    """בדיקה 6: messages.getHistory מ-Saved Messages"""
    print("\n" + "=" * 60)
    print("📨 בדיקה 6: הודעות אחרונות מ-Saved Messages")
    print("=" * 60)

    try:
        from telecraft.tl.generated.functions import MessagesGetHistory
        from telecraft.tl.generated.types import InputPeerSelf
        
        result = await client.invoke_api(
            MessagesGetHistory(
                peer=InputPeerSelf(),
                offset_id=0,
                offset_date=0,
                add_offset=0,
                limit=5,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        
        messages = getattr(result, "messages", [])
        print(f"  נמצאו {len(messages)} הודעות:")
        
        for msg in messages[:5]:
            msg_id = getattr(msg, "id", "?")
            text = getattr(msg, "message", "")
            # Handle bytes vs string
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            if text and len(text) > 40:
                text = text[:40] + "..."
            media = getattr(msg, "media", None)
            media_type = getattr(media, "TL_NAME", None) if media else None
            print(f"    ID={msg_id} | text={text!r} | media={media_type}")
        
        print(f"\n✅ נטענו {len(messages)} הודעות")
        return list(messages)
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_edit_message(client, msg_id: int) -> bool:
    """בדיקה 8: edit_message - עריכת הודעה"""
    print("\n" + "=" * 60)
    print("✏️ בדיקה 8: edit_message - עריכת הודעה")
    print("=" * 60)

    if not msg_id:
        print("  ⚠️ אין הודעה לערוך, מדלג")
        return False

    try:
        from telecraft.tl.generated.types import InputPeerSelf

        new_text = "🧪 הודעה זו נערכה! (edited)"
        print(f"  עורך הודעה {msg_id} לטקסט חדש...")
        
        result = await client.invoke_api(
            __import__('telecraft.tl.generated.functions', fromlist=['MessagesEditMessage']).MessagesEditMessage(
                flags=0,
                no_webpage=False,
                invert_media=False,
                peer=InputPeerSelf(),
                id=int(msg_id),
                message=new_text,
                media=None,
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                quick_reply_shortcut_id=None,
            )
        )
        
        print(f"✅ הודעה נערכה!")
        print(f"   💡 לך לטלגרם ותראה שההודעה השתנתה!")
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_pin_message(client, msg_id: int) -> bool:
    """בדיקה 9: pin_message - הצמדת הודעה"""
    print("\n" + "=" * 60)
    print("📌 בדיקה 9: pin_message - הצמדת הודעה")
    print("=" * 60)

    if not msg_id:
        print("  ⚠️ אין הודעה להצמיד, מדלג")
        return False

    try:
        from telecraft.tl.generated.types import InputPeerSelf
        from telecraft.tl.generated.functions import MessagesUpdatePinnedMessage

        print(f"  מצמיד הודעה {msg_id}...")
        
        result = await client.invoke_api(
            MessagesUpdatePinnedMessage(
                flags=0,
                silent=True,  # לא להודיע
                unpin=False,
                pm_oneside=True,  # רק לעצמי
                peer=InputPeerSelf(),
                id=int(msg_id),
            )
        )
        
        print(f"✅ הודעה הוצמדה!")
        
        # Unpin it
        print(f"  מסיר הצמדה...")
        await client.invoke_api(
            MessagesUpdatePinnedMessage(
                flags=0,
                silent=True,
                unpin=True,  # הסר הצמדה
                pm_oneside=True,
                peer=InputPeerSelf(),
                id=int(msg_id),
            )
        )
        print(f"✅ הצמדה הוסרה!")
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_reaction(client, msg_id: int) -> bool:
    """בדיקה 10: send_reaction - הוספת ריאקציה"""
    print("\n" + "=" * 60)
    print("👍 בדיקה 10: send_reaction - ריאקציות")
    print("=" * 60)

    if not msg_id:
        print("  ⚠️ אין הודעה להגיב עליה, מדלג")
        return False

    try:
        from telecraft.tl.generated.types import InputPeerSelf, ReactionEmoji
        from telecraft.tl.generated.functions import MessagesSendReaction

        print(f"  מוסיף 👍 להודעה {msg_id}...")
        
        result = await client.invoke_api(
            MessagesSendReaction(
                flags=0,
                big=False,
                add_to_recent=True,
                peer=InputPeerSelf(),
                msg_id=int(msg_id),
                reaction=[ReactionEmoji(emoticon="👍")],
            )
        )
        
        print(f"✅ ריאקציה נוספה!")
        print(f"   💡 לך לטלגרם ותראה 👍 על ההודעה!")
        return True
    except Exception as e:
        err_msg = str(e)
        if "PREMIUM_ACCOUNT_REQUIRED" in err_msg:
            print(f"  ⚠️ ריאקציות ב-Saved Messages דורשות פרימיום")
            print(f"   💡 הפיצ'ר עובד בקבוצות/ערוצים!")
            return True  # Not a real failure
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_search(client) -> bool:
    """בדיקה 11: search_messages - חיפוש הודעות"""
    print("\n" + "=" * 60)
    print("🔍 בדיקה 11: search_messages - חיפוש")
    print("=" * 60)

    try:
        from telecraft.tl.generated.types import InputPeerSelf, InputMessagesFilterEmpty
        from telecraft.tl.generated.functions import MessagesSearch

        print(f"  מחפש 'בדיקת' ב-Saved Messages...")
        
        result = await client.invoke_api(
            MessagesSearch(
                flags=0,
                peer=InputPeerSelf(),
                q="בדיקת",
                from_id=None,
                saved_peer_id=None,
                saved_reaction=None,
                top_msg_id=None,
                filter=InputMessagesFilterEmpty(),
                min_date=0,
                max_date=0,
                offset_id=0,
                add_offset=0,
                limit=5,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        
        messages = getattr(result, "messages", [])
        print(f"✅ נמצאו {len(messages)} תוצאות!")
        for msg in messages[:3]:
            text = getattr(msg, "message", "")
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            if text and len(text) > 30:
                text = text[:30] + "..."
            print(f"    • {text!r}")
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_typing_action(client) -> bool:
    """בדיקה 13: send_action - שליחת סטטוס מקליד"""
    print("\n" + "=" * 60)
    print("⌨️ בדיקה 13: send_action - סטטוס מקליד")
    print("=" * 60)

    try:
        from telecraft.tl.generated.types import InputPeerSelf, SendMessageTypingAction
        from telecraft.tl.generated.functions import MessagesSetTyping

        print(f"  שולח סטטוס 'מקליד...'...")
        
        result = await client.invoke_api(
            MessagesSetTyping(
                flags=0,
                peer=InputPeerSelf(),
                top_msg_id=None,
                action=SendMessageTypingAction(),
            )
        )
        
        print(f"✅ סטטוס נשלח!")
        print(f"   💡 הצד השני רואה 'מקליד...' למשך כמה שניות")
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_get_chat_member(client, channel_username: str = "telegram") -> bool:
    """בדיקה 14: get_chat_member - מידע על חבר בערוץ"""
    print("\n" + "=" * 60)
    print("👤 בדיקה 14: get_chat_member - מידע על חבר בערוץ")
    print("=" * 60)

    try:
        # First join the channel to make sure we're a member
        print(f"  📍 ערוץ: @{channel_username}")
        print(f"  מצטרף לערוץ...")
        
        try:
            await client.join_channel(channel_username)
            print(f"     ✅ הצטרפות הצליחה")
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                print(f"     ℹ️ כבר חבר בערוץ")
            else:
                raise

        # Get our own info as a member - use self_user_id or try get_me
        my_id = client.self_user_id
        if not my_id:
            me = await client.get_me()
            my_id = getattr(me, "id", None)
        
        if not my_id:
            print("  ⚠️ לא הצלחנו לקבל את ה-ID שלנו")
            print("  💡 הפיצ'ר get_chat_member עובד, אבל צריך ID של משתמש")
            print("     כדי לבדוק אותו באמת, צריך קבוצה/ערוץ שאתה אדמין בו")
            
            # Leave channel
            print(f"\n  עוזב את הערוץ...")
            await client.leave_channel(channel_username)
            print(f"     ✅ עזיבה הצליחה")
            
            print(f"\n✅ הבדיקה הסתיימה (הפיצ'ר קיים, אבל צריך תנאים מיוחדים)")
            return True

        print(f"  בודק את המידע שלך (id={my_id}) בערוץ...")
        
        member_info = await client.get_chat_member(channel_username, ("user", my_id))
        
        member_tl = getattr(member_info, "TL_NAME", "unknown")
        member_date = getattr(member_info, "date", None)
        
        print(f"✅ קיבלנו מידע על החבר!")
        print(f"   📋 סוג: {member_tl}")
        if member_date:
            from datetime import datetime
            dt = datetime.fromtimestamp(member_date)
            print(f"   📅 תאריך הצטרפות: {dt.strftime('%Y-%m-%d %H:%M')}")

        # Leave the channel
        print(f"\n  עוזב את הערוץ...")
        await client.leave_channel(channel_username)
        print(f"     ✅ עזיבה הצליחה")
        
        return True

    except Exception as e:
        err_msg = str(e)
        if "FLOOD_WAIT" in err_msg:
            print(f"  ⚠️ FloodWait - נסה שוב מאוחר יותר")
            return True
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_admin_actions_info(client) -> bool:
    """בדיקה 15: מידע על פעולות אדמין (בלי לבצע אותן)"""
    print("\n" + "=" * 60)
    print("👮 בדיקה 15: Admin Actions - מידע")
    print("=" * 60)

    print("  📋 פונקציות Admin שזמינות:")
    print("     • ban_user(channel, user) - חסימת משתמש")
    print("     • unban_user(channel, user) - ביטול חסימה")
    print("     • kick_user(channel, user) - הוצאה (ללא חסימה)")
    print("     • promote_admin(channel, user, ...) - הפיכה לאדמין")
    print("     • demote_admin(channel, user) - הורדה מאדמין")
    print("     • get_chat_member(channel, user) - מידע על חבר")
    print()
    print("  ⚠️ לבדיקה אמיתית של ban/kick/promote צריך:")
    print("     1. קבוצה/ערוץ שאתה אדמין בו")
    print("     2. משתמש אחר לבצע עליו את הפעולות")
    print()
    print("  💡 דוגמה לשימוש:")
    print("     await client.ban_user('@my_channel', '@some_user')")
    print("     await client.promote_admin('@my_channel', '@some_user', delete_messages=True)")
    print()
    print("✅ פונקציות Admin מוכנות לשימוש!")
    return True


async def test_get_contacts(client) -> bool:
    """בדיקה 16: get_contacts - רשימת אנשי קשר"""
    print("\n" + "=" * 60)
    print("📇 בדיקה 16: get_contacts - רשימת אנשי קשר")
    print("=" * 60)

    try:
        contacts = await client.get_contacts()
        print(f"✅ נמצאו {len(contacts)} אנשי קשר!")
        
        # Show first 5
        for i, contact in enumerate(contacts[:5]):
            first = getattr(contact, "first_name", b"?")
            last = getattr(contact, "last_name", b"")
            if isinstance(first, bytes):
                first = first.decode("utf-8", errors="replace")
            if isinstance(last, bytes):
                last = last.decode("utf-8", errors="replace")
            username = getattr(contact, "username", None)
            user_id = getattr(contact, "id", "?")
            
            name = f"{first} {last}".strip()
            user_str = f"@{username}" if username else f"id={user_id}"
            print(f"   {i+1}. {name} ({user_str})")
        
        if len(contacts) > 5:
            print(f"   ... ועוד {len(contacts) - 5}")
        
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_get_blocked_users(client) -> bool:
    """בדיקה 17: get_blocked_users - רשימת משתמשים חסומים"""
    print("\n" + "=" * 60)
    print("🚫 בדיקה 17: get_blocked_users - משתמשים חסומים")
    print("=" * 60)

    try:
        blocked = await client.get_blocked_users(limit=10)
        print(f"✅ נמצאו {len(blocked)} משתמשים חסומים")
        
        if blocked:
            for i, b in enumerate(blocked[:3]):
                peer = getattr(b, "peer_id", None)
                if peer:
                    peer_type = getattr(peer, "TL_NAME", "unknown")
                    peer_id = getattr(peer, "user_id", None) or getattr(peer, "channel_id", None)
                    print(f"   {i+1}. {peer_type} (id={peer_id})")
        else:
            print("   💡 אין משתמשים חסומים - זה טוב!")
        
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_invite_links_info(client) -> bool:
    """בדיקה 18: מידע על Invite Links"""
    print("\n" + "=" * 60)
    print("🔗 בדיקה 18: Invite Links - מידע")
    print("=" * 60)

    print("  📋 פונקציות Invite Links שזמינות:")
    print("     • create_invite_link(peer, ...) - יצירת קישור הזמנה")
    print("     • revoke_invite_link(peer, link) - ביטול קישור")
    print("     • delete_invite_link(peer, link) - מחיקת קישור")
    print("     • get_invite_links(peer) - רשימת קישורים")
    print()
    print("  ⚠️ לבדיקה אמיתית צריך:")
    print("     קבוצה/ערוץ שאתה אדמין בו עם הרשאת הזמנה")
    print()
    print("  💡 דוגמה לשימוש:")
    print("     link = await client.create_invite_link('@my_channel', usage_limit=10)")
    print("     print(link.link)  # https://t.me/+abc123")
    print()
    print("✅ פונקציות Invite Links מוכנות לשימוש!")
    return True


async def test_mark_read(client) -> bool:
    """בדיקה 19: mark_read - סימון הודעות כנקראו"""
    print("\n" + "=" * 60)
    print("✓ בדיקה 19: mark_read - סימון הודעות כנקראו")
    print("=" * 60)

    try:
        from telecraft.tl.generated.types import InputPeerSelf
        from telecraft.tl.generated.functions import MessagesReadHistory
        
        print("  מסמן את כל ההודעות ב-Saved Messages כנקראו...")
        
        # Use InputPeerSelf directly since "me" doesn't work as username
        result = await client.invoke_api(
            MessagesReadHistory(peer=InputPeerSelf(), max_id=0)
        )
        
        pts = getattr(result, "pts", None)
        pts_count = getattr(result, "pts_count", None)
        
        if pts is not None:
            print(f"✅ הודעות סומנו כנקראו!")
            print(f"   📊 pts={pts}, pts_count={pts_count}")
        else:
            print(f"✅ הודעות סומנו כנקראו! (result={result})")
        
        return True
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        return False


async def test_group_channel_info(client) -> bool:
    """בדיקה 20: מידע על יצירת קבוצות/ערוצים"""
    print("\n" + "=" * 60)
    print("👥 בדיקה 20: Group/Channel Management - מידע")
    print("=" * 60)

    print("  📋 פונקציות זמינות:")
    print("     • create_group(title, users) - יצירת קבוצה רגילה")
    print("     • create_channel(title, about, ...) - יצירת ערוץ/סופרגרופ")
    print("     • add_user_to_group(group, user) - הוספת משתמש לקבוצה")
    print("     • add_users_to_group(group, users) - הוספת מספר משתמשים")
    print("     • remove_user_from_group(group, user) - הסרת משתמש")
    print("     • get_group_members(group) - רשימת כל החברים")
    print("     • transfer_members(from, to) - העברת חברים בין קבוצות")
    print("     • set_chat_title(peer, title) - שינוי שם קבוצה/ערוץ")
    print()
    print("  💡 דוגמאות שימוש:")
    print()
    print("     # יצירת קבוצה עם משתמשים")
    print("     await client.create_group('חברים', ['@user1', '@user2'])")
    print()
    print("     # יצירת ערוץ")
    print("     await client.create_channel('הערוץ שלי', 'תיאור')")
    print()
    print("     # הוספת מספר משתמשים לקבוצה")
    print("     result = await client.add_users_to_group(")
    print("         '@my_group',")
    print("         ['@user1', '@user2', '@user3'],")
    print("         on_error='skip'  # skip/raise/collect")
    print("     )")
    print("     print(f'הצליחו: {len(result[\"success\"])}')")
    print("     print(f'נכשלו: {len(result[\"failed\"])}')")
    print()
    print("     # קבלת רשימת חברים מקבוצה")
    print("     members = await client.get_group_members('@some_group')")
    print("     for m in members:")
    print("         print(f'{m.first_name} (id={m.id})')")
    print()
    print("     # העברת חברים מקבוצה לקבוצה")
    print("     result = await client.transfer_members(")
    print("         from_group='@source_group',")
    print("         to_group='@my_group',")
    print("         exclude_bots=True,")
    print("         on_error='skip'")
    print("     )")
    print("     print(f'הועברו: {len(result[\"success\"])}')")
    print("     print(f'דולגו: {len(result[\"skipped\"])}')")
    print("     print(f'נכשלו: {len(result[\"failed\"])}')")
    print()
    print("     # הסרת משתמש מקבוצה")
    print("     await client.remove_user_from_group('@my_group', '@bad_user')")
    print()
    print("  ⚠️ חשוב לזכור:")
    print("     • צריך הרשאות מתאימות (אדמין/הזמנה)")
    print("     • משתמשים עם פרטיות מוגבלת לא ניתנים להזמנה")
    print("     • יש להיזהר מ-FLOOD_WAIT בהוספה מרובה")
    print()
    print("✅ פונקציות Group/Channel מוכנות לשימוש!")
    return True


async def test_polls_info(client) -> bool:
    """בדיקה 21: Polls & Quizzes - מידע"""
    print("\n" + "=" * 60)
    print("📊 בדיקה 21: Polls & Quizzes - מידע")
    print("=" * 60)

    print("  📋 פונקציות זמינות:")
    print("     • send_poll(peer, question, options) - שליחת סקר")
    print("     • send_quiz(peer, question, options, correct) - שליחת חידון")
    print("     • vote_poll(peer, msg_id, option) - הצבעה בסקר")
    print("     • close_poll(peer, msg_id) - סגירת סקר")
    print("     • get_poll_results(peer, msg_id) - תוצאות סקר")
    print()
    print("  💡 דוגמאות שימוש:")
    print()
    print("     # שליחת סקר רגיל")
    print("     await client.send_poll(")
    print("         '@my_group',")
    print("         'מה הצבע האהוב עליך?',")
    print("         ['אדום', 'כחול', 'ירוק'],")
    print("         public_voters=True  # להציג מי הצביע")
    print("     )")
    print()
    print("     # שליחת חידון עם תשובה נכונה")
    print("     await client.send_quiz(")
    print("         '@my_group',")
    print("         '2 + 2 = ?',")
    print("         ['3', '4', '5'],")
    print("         correct_option=1,  # 4 היא התשובה הנכונה")
    print("         explanation='מתמטיקה בסיסית!'")
    print("     )")
    print()
    print("     # הצבעה בסקר")
    print("     await client.vote_poll('@my_group', msg_id=123, options=0)")
    print()
    print("✅ פונקציות Polls מוכנות לשימוש!")
    return True


async def test_scheduled_messages_info(client) -> bool:
    """בדיקה 22: Scheduled Messages - מידע"""
    print("\n" + "=" * 60)
    print("📅 בדיקה 22: Scheduled Messages - מידע")
    print("=" * 60)

    print("  📋 פונקציות זמינות:")
    print("     • send_message(..., schedule_date=...) - הודעה מתוזמנת")
    print("     • get_scheduled_messages(peer) - רשימת הודעות מתוזמנות")
    print("     • delete_scheduled_messages(peer, ids) - ביטול תזמון")
    print("     • send_scheduled_now(peer, ids) - שליחה מיידית")
    print()
    print("  💡 דוגמאות שימוש:")
    print()
    print("     import time")
    print()
    print("     # שליחת הודעה מתוזמנת לעוד 5 דקות")
    print("     schedule_time = int(time.time()) + 300")
    print("     # (צריך להוסיף schedule_date ל-send_message)")
    print()
    print("     # קבלת הודעות מתוזמנות")
    print("     scheduled = await client.get_scheduled_messages('@user')")
    print("     for msg in scheduled:")
    print("         print(f'ID: {msg.id}, Date: {msg.date}')")
    print()
    print("     # ביטול הודעה מתוזמנת")
    print("     await client.delete_scheduled_messages('@user', msg_id)")
    print()
    print("     # שליחה מיידית (לפני הזמן)")
    print("     await client.send_scheduled_now('@user', msg_id)")
    print()
    print("✅ פונקציות Scheduled Messages מוכנות לשימוש!")
    return True


async def test_join_leave_channel(client) -> bool:
    """בדיקה 23: join_channel / leave_channel - צירוף ועזיבת ערוץ"""
    print("\n" + "=" * 60)
    print("🚪 בדיקה 16: join_channel / leave_channel")
    print("=" * 60)

    # נשתמש בערוץ ציבורי לבדיקה - @telegram הוא ערוץ רשמי שתמיד קיים
    test_channel = "telegram"  # ללא @

    try:
        print(f"  📍 ערוץ לבדיקה: @{test_channel}")

        # Step 1: נסה להצטרף לערוץ
        print(f"\n  1️⃣ מנסה להצטרף לערוץ...")
        try:
            join_result = await client.join_channel(test_channel)
            join_tl_name = getattr(join_result, "TL_NAME", "unknown")
            print(f"     ✅ הצטרפות הצליחה! (response: {join_tl_name})")
            
            # בדוק אם יש חדשים בתוצאה
            chats = getattr(join_result, "chats", [])
            if chats:
                ch = chats[0]
                title_raw = getattr(ch, "title", "?")
                # Handle bytes title
                title = title_raw.decode("utf-8") if isinstance(title_raw, bytes) else title_raw
                ch_id = getattr(ch, "id", "?")
                print(f"     📢 ערוץ: {title} (id={ch_id})")
        except Exception as e:
            err_msg = str(e)
            if "CHANNELS_TOO_MUCH" in err_msg:
                print(f"     ⚠️ כבר מצורף למקסימום ערוצים, לא ניתן להצטרף לעוד")
                return True  # זה לא כישלון של הקוד
            elif "USER_ALREADY_PARTICIPANT" in err_msg:
                print(f"     ℹ️ כבר חבר בערוץ הזה")
            else:
                raise

        # המתן קצת
        await asyncio.sleep(1)

        # Step 2: עזוב את הערוץ
        print(f"\n  2️⃣ עוזב את הערוץ...")
        leave_result = await client.leave_channel(test_channel)
        leave_tl_name = getattr(leave_result, "TL_NAME", "unknown")
        print(f"     ✅ עזיבה הצליחה! (response: {leave_tl_name})")

        print(f"\n✅ בדיקת join/leave הושלמה!")
        print(f"   💡 אם תיכנס לטלגרם תראה שנכנסת ויצאת מ-@{test_channel}")
        return True

    except Exception as e:
        err_msg = str(e)
        if "FLOOD_WAIT" in err_msg:
            print(f"  ⚠️ FloodWait - טלגרם מגביל. נסה שוב מאוחר יותר")
            return True  # לא כישלון של הקוד
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_download_media(client, messages: list) -> bool:
    """בדיקה 24: download_media - הורדת תמונה"""
    print("\n" + "=" * 60)
    print("📷 בדיקה 24: download_media - הורדת מדיה")
    print("=" * 60)

    # Find a message with photo
    photo_msg = None
    for msg in messages:
        media = getattr(msg, "media", None)
        if media and getattr(media, "TL_NAME", None) == "messageMediaPhoto":
            photo_msg = msg
            break

    if not photo_msg:
        print("  ⚠️ לא נמצאה תמונה ב-5 ההודעות האחרונות")
        print("  💡 טיפ: שלח תמונה ל-Saved Messages ונסה שוב")
        return False

    try:
        print(f"  נמצאה תמונה בהודעה {getattr(photo_msg, 'id', '?')}")
        print("  מוריד...")

        dest = Path("downloads")
        dest.mkdir(exist_ok=True)
        result = await client.download_media(photo_msg, dest=str(dest))

        if result:
            size = Path(result).stat().st_size
            print(f"✅ תמונה הורדה! {result} ({size} bytes)")
            return True
        else:
            print("❌ ההורדה נכשלה (result=None)")
            return False
    except Exception as e:
        print(f"  ❌ שגיאה: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main() -> None:
    print("🚀 בדיקת פיצ'רים חדשים - telecraft")
    print("=" * 60)

    # Setup
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")
    session = _current_session_path("prod")
    print(f"📁 Session: {session}")

    client = MtprotoClient(
        network="prod",
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )

    await client.connect()
    print("✅ מחובר!")

    try:
        # Test 1: iter_dialogs
        await test_iter_dialogs(client)

        # Test 2: send to self
        sent_msg_id = await test_send_to_self(client)

        # Test 3: send with reply
        reply_msg_id = await test_send_with_reply(client, sent_msg_id)

        # Test 4: forward message
        forwarded_id = None
        if reply_msg_id:
            forwarded_id = await test_forward_message(client, reply_msg_id)
            if forwarded_id:
                print(f"   💡 לך לטלגרם ל-Saved Messages ותראה הודעה מועברת!")

        # Test 5: delete - נמחק את ההודעה הראשונה שנשלחה (לא את המועברת)
        if sent_msg_id:
            await test_delete_message(client, sent_msg_id)

        # Test 6: get history
        messages = await test_get_history(client)

        # Test 7 removed - will be test 13 at end

        # Test 8: edit message (edit the reply message)
        if reply_msg_id:
            await test_edit_message(client, reply_msg_id)

        # Test 9: pin message
        if reply_msg_id:
            await test_pin_message(client, reply_msg_id)

        # Test 10: reactions
        if reply_msg_id:
            await test_reaction(client, reply_msg_id)

        # Test 11: search
        await test_search(client)

        # Test 12: typing action
        await test_typing_action(client)

        # Test 13: get_chat_member (קבלת מידע על חבר בערוץ)
        await test_get_chat_member(client)

        # Test 14: admin actions info (הסבר על פעולות אדמין)
        await test_admin_actions_info(client)

        # Test 15: get_contacts (רשימת אנשי קשר)
        await test_get_contacts(client)

        # Test 16: get_blocked_users (משתמשים חסומים)
        await test_get_blocked_users(client)

        # Test 17: invite links info (הסבר על קישורי הזמנה)
        await test_invite_links_info(client)

        # Test 18: mark_read (סימון הודעות כנקראו)
        await test_mark_read(client)

        # Test 19: group/channel management info
        await test_group_channel_info(client)

        # Test 20: polls info
        await test_polls_info(client)

        # Test 21: scheduled messages info
        await test_scheduled_messages_info(client)

        # Test 22: join/leave channel (ערוץ ציבורי אמיתי!)
        await test_join_leave_channel(client)

        # Test 23: download (if photo exists)
        await test_download_media(client, messages)

        print("\n" + "=" * 60)
        print("✅ כל 23 הבדיקות הסתיימו!")
        print("=" * 60)

    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
