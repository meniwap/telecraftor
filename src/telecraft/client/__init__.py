from __future__ import annotations

from .account import AuthorizationRef, ThemeRef, WallpaperRef, WebAuthorizationRef
from .admin import ADMIN_RIGHTS_BASIC, banned_rights_full_ban, make_admin_rights, make_banned_rights
from .calls import (
    CallParticipantRef,
    GroupCallJoinParams,
    GroupCallRef,
    JoinAsRef,
    PhoneCallRef,
)
from .chatlists import ChatlistRef
from .client import Client
from .folders import FolderAssignment
from .gifts import GiftRef
from .messages import ReplyToMessageRef, ReplyToStoryRef
from .mtproto import ClientInit
from .notifications import NotifyTarget
from .payments import InvoiceRef, StarsAmountRef
from .peers import Peer, PeerRef, PeerType
from .privacy import PrivacyKey, PrivacyRuleBuilder
from .reports import ReportReasonBuilder
from .stickers import DocumentRef, StickerSetRef
from .takeout import TakeoutScopes, TakeoutSessionRef

__all__ = [
    "ADMIN_RIGHTS_BASIC",
    "AuthorizationRef",
    "CallParticipantRef",
    "ChatlistRef",
    "Client",
    "ClientInit",
    "DocumentRef",
    "GiftRef",
    "GroupCallJoinParams",
    "GroupCallRef",
    "InvoiceRef",
    "JoinAsRef",
    "NotifyTarget",
    "Peer",
    "PeerRef",
    "PeerType",
    "PhoneCallRef",
    "PrivacyKey",
    "PrivacyRuleBuilder",
    "ReplyToMessageRef",
    "ReplyToStoryRef",
    "ReportReasonBuilder",
    "FolderAssignment",
    "StickerSetRef",
    "StarsAmountRef",
    "TakeoutScopes",
    "TakeoutSessionRef",
    "ThemeRef",
    "WallpaperRef",
    "WebAuthorizationRef",
    "banned_rights_full_ban",
    "make_admin_rights",
    "make_banned_rights",
]
