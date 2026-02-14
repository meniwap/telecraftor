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
from .passkeys import PasskeyCredential, PasskeyRef
from .payments import InvoiceRef, StarsAmountRef
from .peers import Peer, PeerRef, PeerType
from .premium import PremiumBoostSlots
from .privacy import PrivacyKey, PrivacyRuleBuilder
from .reports import ReportReasonBuilder
from .stickers import DocumentRef, StickerSetRef
from .sponsored import SponsoredMessageRef, SponsoredReportOption
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
    "PasskeyCredential",
    "PasskeyRef",
    "Peer",
    "PeerRef",
    "PeerType",
    "PhoneCallRef",
    "PremiumBoostSlots",
    "PrivacyKey",
    "PrivacyRuleBuilder",
    "ReplyToMessageRef",
    "ReplyToStoryRef",
    "ReportReasonBuilder",
    "FolderAssignment",
    "StickerSetRef",
    "StarsAmountRef",
    "SponsoredMessageRef",
    "SponsoredReportOption",
    "TakeoutScopes",
    "TakeoutSessionRef",
    "ThemeRef",
    "WallpaperRef",
    "WebAuthorizationRef",
    "banned_rights_full_ban",
    "make_admin_rights",
    "make_banned_rights",
]
