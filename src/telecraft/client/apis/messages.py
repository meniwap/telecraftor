from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.messages import build_input_reply_to_message, build_input_reply_to_story
from telecraft.client.peers import PeerRef
from telecraft.client.stickers import DocumentRef, build_input_document
from telecraft.tl.generated.functions import (
    MessagesCheckHistoryImportPeer,
    MessagesDeleteScheduledMessages,
    MessagesGetAvailableEffects,
    MessagesGetDiscussionMessage,
    MessagesGetMessageEditData,
    MessagesGetMessageReadParticipants,
    MessagesGetMessagesViews,
    MessagesGetOutboxReadDate,
    MessagesGetPaidReactionPrivacy,
    MessagesGetReplies,
    MessagesGetSavedGifs,
    MessagesGetScheduledHistory,
    MessagesGetUnreadMentions,
    MessagesGetUnreadReactions,
    MessagesGetWebPagePreview,
    MessagesReadDiscussion,
    MessagesReadMentions,
    MessagesReadMessageContents,
    MessagesReadReactions,
    MessagesReportMessagesDelivery,
    MessagesSaveGif,
    MessagesSearchSentMedia,
    MessagesSendInlineBotResult,
    MessagesSendMedia,
    MessagesSendMessage,
    MessagesSendPaidReaction,
    MessagesSendScheduledMessages,
    MessagesSendScreenshotNotification,
    MessagesTogglePaidReactionPrivacy,
)
from telecraft.tl.generated.types import InputMediaWebPage, InputMessagesFilterEmpty

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class MessagesScheduledAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetScheduledHistory(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                hash=0,
            ),
            timeout=timeout,
        )

    async def send_now(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesSendScheduledMessages(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
            ),
            timeout=timeout,
        )

    async def delete(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesDeleteScheduledMessages(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
            ),
            timeout=timeout,
        )


class MessagesWebAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def preview(
        self,
        message: str,
        *,
        entities: Sequence[Any] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 8 if entities is not None else 0
        return await self._raw.invoke_api(
            MessagesGetWebPagePreview(
                flags=flags,
                message=str(message),
                entities=list(entities) if entities is not None else None,
            ),
            timeout=timeout,
        )

    async def send(
        self,
        peer: PeerRef,
        url: str,
        *,
        text: str = "",
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        force_large: bool = False,
        force_small: bool = False,
        optional: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)

        media_flags = 0
        if force_large:
            media_flags |= 1
        if force_small:
            media_flags |= 2
        if optional:
            media_flags |= 4

        reply_to = None
        flags = 0
        if reply_to_msg_id is not None:
            flags |= 1
            reply_to = build_input_reply_to_message(int(reply_to_msg_id))
        if silent:
            flags |= 32

        return await self._raw.invoke_api(
            MessagesSendMedia(
                flags=flags,
                silent=True if silent else None,
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=input_peer,
                reply_to=reply_to,
                media=InputMediaWebPage(
                    flags=media_flags,
                    force_large_media=True if force_large else None,
                    force_small_media=True if force_small else None,
                    optional=True if optional else None,
                    url=str(url),
                ),
                message=str(text),
                random_id=secrets.randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )

    async def send_large(
        self,
        peer: PeerRef,
        url: str,
        *,
        text: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.send(
            peer,
            url,
            text=text,
            force_large=True,
            timeout=timeout,
        )

    async def send_small(
        self,
        peer: PeerRef,
        url: str,
        *,
        text: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.send(
            peer,
            url,
            text=text,
            force_small=True,
            timeout=timeout,
        )

    async def send_optional(
        self,
        peer: PeerRef,
        url: str,
        *,
        text: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.send(
            peer,
            url,
            text=text,
            optional=True,
            timeout=timeout,
        )


class MessagesDiscussionAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def replies(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetReplies(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                offset_id=int(offset_id),
                offset_date=0,
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
                hash=0,
            ),
            timeout=timeout,
        )

    async def message(self, peer: PeerRef, msg_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetDiscussionMessage(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def read(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        read_max_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesReadDiscussion(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                read_max_id=int(read_max_id),
            ),
            timeout=timeout,
        )


class MessagesReceiptsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def views(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        *,
        increment: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesGetMessagesViews(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
                increment=bool(increment),
            ),
            timeout=timeout,
        )

    async def read_participants(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetMessageReadParticipants(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def outbox_read_date(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetOutboxReadDate(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def read_contents(
        self,
        msg_ids: int | Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesReadMessageContents(id=ids),
            timeout=timeout,
        )

    async def screenshot_notify(
        self,
        peer: PeerRef,
        reply_to_msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesSendScreenshotNotification(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reply_to=build_input_reply_to_message(int(reply_to_msg_id)),
                random_id=secrets.randbits(63),
            ),
            timeout=timeout,
        )

    async def report_delivery(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        *,
        push: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if push else 0
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesReportMessagesDelivery(
                flags=flags,
                push=True if push else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
            ),
            timeout=timeout,
        )


class MessagesEffectsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetAvailableEffects(hash=int(hash)),
            timeout=timeout,
        )

    async def send_text(
        self,
        peer: PeerRef,
        text: str,
        effect_id: int,
        *,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if silent:
            flags |= 32
        return await self._raw.invoke_api(
            MessagesSendMessage(
                flags=flags,
                no_webpage=False,
                silent=True if silent else None,
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reply_to=None,
                message=str(text),
                random_id=secrets.randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=int(effect_id),
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )

    async def send_media(
        self,
        peer: PeerRef,
        media: Any,
        *,
        text: str = "",
        effect_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if silent:
            flags |= 32
        if effect_id is not None:
            flags |= 1 << 18
        return await self._raw.invoke_api(
            MessagesSendMedia(
                flags=flags,
                silent=True if silent else None,
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reply_to=None,
                media=media,
                message=str(text),
                random_id=secrets.randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=int(effect_id) if effect_id is not None else None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )


class MessagesSentMediaAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def search(
        self,
        peer: PeerRef,
        *,
        q: str = "",
        filter: Any | None = None,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        _ = (
            await resolve_input_peer(self._raw, peer, timeout=timeout),
            int(offset_id),
            int(add_offset),
            int(max_id),
            int(min_id),
        )
        return await self._raw.invoke_api(
            MessagesSearchSentMedia(
                q=str(q),
                filter=filter if filter is not None else InputMessagesFilterEmpty(),
                limit=int(limit),
            ),
            timeout=timeout,
        )


class MessagesGifsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def saved_list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetSavedGifs(hash=int(hash)), timeout=timeout)

    async def save(
        self,
        document: DocumentRef | Any,
        *,
        unsave: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesSaveGif(id=build_input_document(document), unsave=bool(unsave)),
            timeout=timeout,
        )


class MessagesPaidReactionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def send(
        self,
        peer: PeerRef,
        msg_id: int,
        count: int,
        *,
        privacy: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if privacy is not None else 0
        return await self._raw.invoke_api(
            MessagesSendPaidReaction(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                count=int(count),
                random_id=secrets.randbits(63),
                private=privacy,
            ),
            timeout=timeout,
        )

    async def get_privacy(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetPaidReactionPrivacy(), timeout=timeout)

    async def set_privacy(
        self,
        peer: PeerRef,
        msg_id: int,
        privacy: Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesTogglePaidReactionPrivacy(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                private=privacy,
            ),
            timeout=timeout,
        )


class MessagesInlineAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def send_result(
        self,
        peer: PeerRef,
        query_id: int,
        result_id: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        reply_to = None
        if reply_to_msg_id is not None:
            flags |= 1
            reply_to = build_input_reply_to_message(int(reply_to_msg_id))
        if silent:
            flags |= 32
        return await self._raw.invoke_api(
            MessagesSendInlineBotResult(
                flags=flags,
                silent=True if silent else None,
                background=False,
                clear_draft=False,
                hide_via=False,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reply_to=reply_to,
                random_id=secrets.randbits(63),
                query_id=int(query_id),
                id=str(result_id),
                schedule_date=None,
                send_as=None,
                quick_reply_shortcut=None,
                allow_paid_stars=None,
            ),
            timeout=timeout,
        )

    async def send_result_reply_to_story(
        self,
        peer: PeerRef,
        query_id: int,
        result_id: str,
        story_peer: PeerRef,
        story_id: int,
        *,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1
        if silent:
            flags |= 32
        return await self._raw.invoke_api(
            MessagesSendInlineBotResult(
                flags=flags,
                silent=True if silent else None,
                background=False,
                clear_draft=False,
                hide_via=False,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reply_to=await build_input_reply_to_story(
                    self._raw,
                    story_peer,
                    int(story_id),
                    timeout=timeout,
                ),
                random_id=secrets.randbits(63),
                query_id=int(query_id),
                id=str(result_id),
                schedule_date=None,
                send_as=None,
                quick_reply_shortcut=None,
                allow_paid_stars=None,
            ),
            timeout=timeout,
        )

    async def edit_data(self, peer: PeerRef, msg_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetMessageEditData(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(msg_id),
            ),
            timeout=timeout,
        )


class MessagesHistoryImportAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def check_peer(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesCheckHistoryImportPeer(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )


class MessagesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.scheduled = MessagesScheduledAPI(raw)
        self.web = MessagesWebAPI(raw)
        self.discussion = MessagesDiscussionAPI(raw)
        self.receipts = MessagesReceiptsAPI(raw)
        self.effects = MessagesEffectsAPI(raw)
        self.sent_media = MessagesSentMediaAPI(raw)
        self.gifs = MessagesGifsAPI(raw)
        self.paid_reactions = MessagesPaidReactionsAPI(raw)
        self.inline = MessagesInlineAPI(raw)
        self.history_import = MessagesHistoryImportAPI(raw)

    async def send(
        self,
        peer: PeerRef,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_self(
        self,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_self(
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_chat(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_chat(
            chat_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_user(
        self,
        user_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_user(
            user_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_channel(
        self,
        channel_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_channel(
            channel_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_peer(
        self,
        peer: Any,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_peer(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def forward(
        self,
        *,
        from_peer: PeerRef,
        to_peer: PeerRef,
        msg_ids: int | list[int],
        drop_author: bool = False,
        drop_captions: bool = False,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.forward_messages(
            from_peer=from_peer,
            to_peer=to_peer,
            msg_ids=msg_ids,
            drop_author=drop_author,
            drop_captions=drop_captions,
            silent=silent,
            timeout=timeout,
        )

    async def delete(
        self,
        peer: PeerRef,
        msg_ids: int | list[int],
        *,
        revoke: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.delete_messages(peer, msg_ids, revoke=revoke, timeout=timeout)

    async def edit(
        self,
        peer: PeerRef,
        msg_id: int,
        text: str,
        *,
        no_webpage: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.edit_message(
            peer,
            msg_id,
            text,
            no_webpage=no_webpage,
            timeout=timeout,
        )

    async def pin(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        unpin: bool = False,
        silent: bool = False,
        pm_oneside: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.pin_message(
            peer,
            msg_id,
            unpin=unpin,
            silent=silent,
            pm_oneside=pm_oneside,
            timeout=timeout,
        )

    async def react(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        reaction: str | list[str] | None = None,
        emoji: str | list[str] | None = None,
        big: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        if reaction is not None and emoji is not None:
            raise ValueError("Pass only one of reaction or emoji")
        resolved = reaction if reaction is not None else emoji
        return await self._raw.send_reaction(
            peer,
            msg_id,
            reaction=resolved,
            big=big,
            timeout=timeout,
        )

    async def search(
        self,
        peer: PeerRef,
        *,
        query: str = "",
        from_user: PeerRef | None = None,
        offset_id: int = 0,
        limit: int = 100,
        min_date: int = 0,
        max_date: int = 0,
        timeout: float = 20.0,
    ) -> list[Any]:
        return await self._raw.search_messages(
            peer,
            query=query,
            from_user=from_user,
            offset_id=offset_id,
            limit=limit,
            min_date=min_date,
            max_date=max_date,
            timeout=timeout,
        )

    async def mark_read(self, peer: PeerRef, *, max_id: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.mark_read(peer, max_id=max_id, timeout=timeout)

    async def unread_mentions(
        self,
        peer: PeerRef,
        *,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        top_msg_id: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if top_msg_id is not None else 0
        return await self._raw.invoke_api(
            MessagesGetUnreadMentions(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id) if top_msg_id is not None else None,
                offset_id=int(offset_id),
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
            ),
            timeout=timeout,
        )

    async def read_mentions(
        self,
        peer: PeerRef,
        *,
        top_msg_id: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if top_msg_id is not None else 0
        return await self._raw.invoke_api(
            MessagesReadMentions(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id) if top_msg_id is not None else None,
            ),
            timeout=timeout,
        )

    async def unread_reactions(
        self,
        peer: PeerRef,
        *,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        top_msg_id: int | None = None,
        saved_peer_id: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if top_msg_id is not None:
            flags |= 1
        saved_peer = None
        if saved_peer_id is not None:
            flags |= 2
            saved_peer = await resolve_input_peer(self._raw, saved_peer_id, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesGetUnreadReactions(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id) if top_msg_id is not None else None,
                saved_peer_id=saved_peer,
                offset_id=int(offset_id),
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
            ),
            timeout=timeout,
        )

    async def read_reactions(
        self,
        peer: PeerRef,
        *,
        top_msg_id: int | None = None,
        saved_peer_id: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if top_msg_id is not None:
            flags |= 1
        saved_peer = None
        if saved_peer_id is not None:
            flags |= 2
            saved_peer = await resolve_input_peer(self._raw, saved_peer_id, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesReadReactions(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id) if top_msg_id is not None else None,
                saved_peer_id=saved_peer,
            ),
            timeout=timeout,
        )

    async def history(
        self,
        peer: PeerRef,
        *,
        limit: int = 50,
        timeout: float = 20.0,
    ) -> list[Any]:
        return await self._raw.get_history(
            peer,
            limit=limit,
            timeout=timeout,
        )

    async def iter_dialogs(
        self,
        *,
        limit: int = 100,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        async for item in self._raw.iter_dialogs(limit=limit, folder_id=folder_id, timeout=timeout):
            yield item

    async def iter_messages(
        self,
        peer: PeerRef,
        *,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        async for item in self._raw.iter_messages(peer, limit=limit, timeout=timeout):
            yield item
