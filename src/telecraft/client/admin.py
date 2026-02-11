from __future__ import annotations

from telecraft.tl.generated.types import ChatAdminRights, ChatBannedRights


def make_admin_rights(
    *,
    change_info: bool = False,
    post_messages: bool = False,
    edit_messages: bool = False,
    delete_messages: bool = False,
    ban_users: bool = False,
    invite_users: bool = False,
    pin_messages: bool = False,
    add_admins: bool = False,
    anonymous: bool = False,
    manage_call: bool = False,
    other: bool = False,
    manage_topics: bool = False,
    post_stories: bool = False,
    edit_stories: bool = False,
    delete_stories: bool = False,
    manage_direct_messages: bool = False,
) -> ChatAdminRights:
    """
    Convenience builder for chatAdminRights.

    Note: For ChatAdminRights, setting a field to True grants that admin capability.
    """
    return ChatAdminRights(
        flags=0,
        change_info=bool(change_info),
        post_messages=bool(post_messages),
        edit_messages=bool(edit_messages),
        delete_messages=bool(delete_messages),
        ban_users=bool(ban_users),
        invite_users=bool(invite_users),
        pin_messages=bool(pin_messages),
        add_admins=bool(add_admins),
        anonymous=bool(anonymous),
        manage_call=bool(manage_call),
        other=bool(other),
        manage_topics=bool(manage_topics),
        post_stories=bool(post_stories),
        edit_stories=bool(edit_stories),
        delete_stories=bool(delete_stories),
        manage_direct_messages=bool(manage_direct_messages),
    )


def make_banned_rights(
    *,
    view_messages: bool = False,
    send_messages: bool = False,
    send_media: bool = False,
    send_stickers: bool = False,
    send_gifs: bool = False,
    send_games: bool = False,
    send_inline: bool = False,
    embed_links: bool = False,
    send_polls: bool = False,
    change_info: bool = False,
    invite_users: bool = False,
    pin_messages: bool = False,
    manage_topics: bool = False,
    send_photos: bool = False,
    send_videos: bool = False,
    send_roundvideos: bool = False,
    send_audios: bool = False,
    send_voices: bool = False,
    send_docs: bool = False,
    send_plain: bool = False,
    until_date: int = 0,
) -> ChatBannedRights:
    """
    Convenience builder for chatBannedRights.

    Note: For ChatBannedRights, setting a field to True BANS that capability.
    (i.e. this is a restrictions mask).
    """
    return ChatBannedRights(
        flags=0,
        view_messages=bool(view_messages),
        send_messages=bool(send_messages),
        send_media=bool(send_media),
        send_stickers=bool(send_stickers),
        send_gifs=bool(send_gifs),
        send_games=bool(send_games),
        send_inline=bool(send_inline),
        embed_links=bool(embed_links),
        send_polls=bool(send_polls),
        change_info=bool(change_info),
        invite_users=bool(invite_users),
        pin_messages=bool(pin_messages),
        manage_topics=bool(manage_topics),
        send_photos=bool(send_photos),
        send_videos=bool(send_videos),
        send_roundvideos=bool(send_roundvideos),
        send_audios=bool(send_audios),
        send_voices=bool(send_voices),
        send_docs=bool(send_docs),
        send_plain=bool(send_plain),
        until_date=int(until_date),
    )


# Simple presets for ergonomics (can expand later).
ADMIN_RIGHTS_BASIC = make_admin_rights(
    change_info=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    manage_topics=True,
)


# Full ban (kick/ban semantics): disallow viewing messages until_date.
def banned_rights_full_ban(*, until_date: int = 0) -> ChatBannedRights:
    return make_banned_rights(view_messages=True, until_date=until_date)
