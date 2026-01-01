from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from telecraft.mtproto.rpc.sender import RpcErrorException


def _need_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(
            f"Missing {name}. Run: source apps/env.sh (or export {name}=...)."
        )
    return v


def _need_env_int(name: str) -> int:
    v = _need_env(name)
    try:
        return int(v)
    except ValueError as e:
        raise SystemExit(f"{name} must be an int") from e


def _default_session(network: str, dc: int) -> str:
    return str(Path(".sessions") / f"{network}_dc{dc}.session.json")

def _current_session_pointer(network: str) -> Path:
    return Path(".sessions") / f"{network}.current"

def _read_current_session(network: str) -> str | None:
    p = _current_session_pointer(network)
    try:
        s = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not s:
        return None
    if Path(s).exists():
        return s
    return None

def _write_current_session(network: str, session_path: str) -> None:
    p = _current_session_pointer(network)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(session_path).strip() + "\n", encoding="utf-8", newline="\n")

def _pick_latest_session(network: str) -> str | None:
    best: tuple[float, str] | None = None
    for dc in (1, 2, 3, 4, 5):
        sp = _default_session(network, dc)
        p = Path(sp)
        if not p.exists():
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, sp)
    return best[1] if best else None

def _pick_existing_session(network: str, preferred_dc: int) -> str:
    """
    Pick a session file to use.
    - Prefer the requested DC file if it exists
    - Otherwise pick the first existing DC session file (1..5)
    - Otherwise return the preferred path (will be created later)
    """
    current = _read_current_session(network)
    if current is not None:
        return current
    preferred = _default_session(network, preferred_dc)
    if Path(preferred).exists():
        return preferred
    latest = _pick_latest_session(network)
    if latest is not None:
        return latest
    return preferred

def _session_client_args(session_path: str) -> tuple[int, str, int, str]:
    from telecraft.mtproto.session import load_session_file

    s = load_session_file(session_path)
    return int(s.dc_id), str(s.host), int(s.port), str(s.framing)


async def _cmd_login(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    phone_number = args.phone or input("Phone number (international): ").strip()
    session = args.session or _pick_existing_session(args.network, args.dc)

    init = ClientInit(api_id=api_id, api_hash=api_hash)

    dc = args.dc
    for attempt in range(2):
        # If we already have a session file, prefer its DC/host/port/framing to avoid mismatch.
        if Path(session).exists():
            dc_from_sess, host, port, framing = _session_client_args(session)
            dc = dc_from_sess
            host_override = host
            port_override = port
            framing_override = framing
        else:
            host_override = None
            port_override = 443
            framing_override = args.framing

        client = MtprotoClient(
            network=args.network,
            dc_id=dc,
            host=host_override,
            port=port_override,
            framing=framing_override,
            session_path=session,
            init=init,
        )
        await client.connect(timeout=args.timeout)
        try:
            sent = await client.send_code(phone_number, timeout=args.timeout)
            print("Sent code. (check Telegram/SMS)")

            phone_code_hash = sent.phone_code_hash
            code = args.code or input("Code: ").strip()
            try:
                auth = await client.sign_in(
                    phone_number=phone_number,
                    phone_code_hash=phone_code_hash,
                    phone_code=code,
                    timeout=args.timeout,
                )
            except RpcErrorException as e:
                if e.message == "SESSION_PASSWORD_NEEDED":
                    pw = args.password or os.environ.get("TELEGRAM_PASSWORD") or input(
                        "2FA password: "
                    ).strip()
                    authz = await client.check_password(pw, timeout=args.timeout)
                    print("Logged in OK.")
                    _ = authz
                    return 0
                raise

            # Logged in
            if getattr(auth, "TL_NAME", None) == "auth.authorization":
                print("Logged in OK.")
                print(f"Session saved to: {session}")
                _write_current_session(args.network, session)
                return 0

            # Sign-up required (new account)
            if getattr(auth, "TL_NAME", None) == "auth.authorizationSignUpRequired":
                first = args.first_name or input("First name: ").strip()
                last = args.last_name or input("Last name (optional): ").strip()
                _ = await client.sign_up(
                    phone_number=phone_number,
                    phone_code_hash=phone_code_hash,
                    first_name=first,
                    last_name=last,
                    timeout=args.timeout,
                )
                print("Signed up + logged in OK.")
                print(f"Session saved to: {session}")
                _write_current_session(args.network, session)
                return 0

            print("Unexpected login result:", repr(auth))
            return 1
        except RpcErrorException as e:
            # Simple DC migrate support (retry once).
            msg = e.message
            for prefix in ("PHONE_MIGRATE_", "USER_MIGRATE_", "NETWORK_MIGRATE_"):
                if prefix in msg:
                    try:
                        dc = int(msg.split(prefix, 1)[1])
                        # New auth_key must be created on the new DC, so use a new session file.
                        session = _default_session(args.network, dc)
                        print(f"Migrating to DC {dc} (next session: {session})...")
                        break
                    except ValueError:
                        pass
            else:
                raise
        finally:
            await client.close()

    return 1


async def _cmd_me(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        me = await client.get_me(timeout=args.timeout)
        print(repr(me))
        return 0
    finally:
        await client.close()


async def _cmd_updates(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        await client.start_updates(timeout=args.timeout)
        print("Listening... (send yourself a message; Ctrl+C to stop)")
        while True:
            u = await client.recv_update()
            print(repr(u))
    finally:
        await client.close()


async def _cmd_send_self(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        res = await client.send_message_self(args.text, timeout=args.timeout)
        print(repr(res))
        return 0
    finally:
        await client.close()

def _parse_peer_arg(raw: str) -> object:
    """
    CLI helper:
      - "@username" / "+1555..." => resolve via network
      - "user:123" / "chat:123" / "channel:123" => explicit peer type
    """
    s = str(raw).strip()
    for prefix in ("user:", "chat:", "channel:"):
        if s.startswith(prefix):
            pt = prefix[:-1]
            rest = s[len(prefix) :].strip()
            return (pt, int(rest))
    return s


async def _cmd_send(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        peer_ref = _parse_peer_arg(args.peer)
        peer = await client.resolve_peer(peer_ref, timeout=args.timeout)
        print(f"Resolved peer: {peer.peer_type}:{peer.peer_id}")
        res = await client.send_message(peer_ref, args.text, timeout=args.timeout)
        print(repr(res))
        return 0
    finally:
        await client.close()


async def _cmd_send_file(args: argparse.Namespace) -> int:
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        peer_ref = _parse_peer_arg(args.peer)
        as_photo: bool | None = None
        if args.as_photo:
            as_photo = True
        if args.as_document:
            as_photo = False
        p = Path(args.path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p)
        p = p.resolve()
        if not p.exists() or not p.is_file():
            raise SystemExit(f"File not found: {p}")
        res = await client.send_file(
            peer_ref,
            str(p),
            caption=args.caption,
            as_photo=as_photo,
            timeout=args.timeout,
        )
        print(repr(res))
        return 0
    finally:
        await client.close()


async def _cmd_download_next_media(args: argparse.Namespace) -> int:
    """
    Convenience demo:
    - start updates
    - wait for the next incoming message with media
    - download_media() into dest
    """
    from telecraft.bot.events import MessageEvent
    from telecraft.client.mtproto import ClientInit, MtprotoClient

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        await client.start_updates(timeout=args.timeout)
        print("Waiting for next message with media... (send yourself a photo/document)")
        poll_interval = 1.0
        last_history_check = 0.0

        async def _fetch_latest_self_msg_id() -> int:
            try:
                from telecraft.tl.generated.functions import MessagesGetHistory
                from telecraft.tl.generated.types import (
                    InputPeerSelf,
                    MessagesMessages,
                    MessagesMessagesSlice,
                )

                hist = await client.invoke_api(
                    MessagesGetHistory(
                        peer=InputPeerSelf(),
                        offset_id=0,
                        offset_date=0,
                        add_offset=0,
                        limit=1,
                        max_id=0,
                        min_id=0,
                        hash=0,
                    ),
                    timeout=args.timeout,
                )
                if isinstance(hist, (MessagesMessages, MessagesMessagesSlice)):
                    msgs = getattr(hist, "messages", None)
                    if isinstance(msgs, list) and msgs:
                        mid = getattr(msgs[0], "id", None)
                        return int(mid) if isinstance(mid, int) else 0
            except Exception:
                return 0
            return 0

        start_id = await _fetch_latest_self_msg_id()

        async def _poll_history_once(*, after_id: int) -> tuple[str | None, int]:
            try:
                from telecraft.tl.generated.functions import MessagesGetHistory
                from telecraft.tl.generated.types import (
                    InputPeerSelf,
                    MessagesMessages,
                    MessagesMessagesSlice,
                )

                hist = await client.invoke_api(
                    MessagesGetHistory(
                        peer=InputPeerSelf(),
                        offset_id=0,
                        offset_date=0,
                        add_offset=0,
                        limit=20,
                        max_id=0,
                        min_id=0,
                        hash=0,
                    ),
                    timeout=args.timeout,
                )
                if isinstance(hist, (MessagesMessages, MessagesMessagesSlice)):
                    msgs = getattr(hist, "messages", None)
                    if isinstance(msgs, list):
                        newest_id = int(after_id)
                        for m in msgs:
                            mid = getattr(m, "id", None)
                            if isinstance(mid, int):
                                newest_id = max(newest_id, int(mid))

                        for m in msgs:
                            mid = getattr(m, "id", None)
                            if not isinstance(mid, int) or int(mid) <= int(after_id):
                                continue
                            got = await client.download_media(m, dest=args.dest, timeout=args.timeout)
                            if got is not None:
                                return str(got), newest_id
                        return None, newest_id
            except Exception:
                return None, int(after_id)
            return None, int(after_id)

        while True:
            # Wait for updates, but don't block forever: Saved Messages may not deliver
            # a rich message update with media, so we also poll history periodically.
            try:
                u = await asyncio.wait_for(client.recv_update(), timeout=poll_interval)
            except asyncio.TimeoutError:
                u = None

            if u is not None:
                out = await client.download_media(u, dest=args.dest, timeout=args.timeout)
                if out is not None:
                    print("Downloaded:", out)
                    return 0

                # Try mapped message event.
                e = MessageEvent.from_update(client=client, update=u)
                if e is not None:
                    out2 = await client.download_media(e, dest=args.dest, timeout=args.timeout)
                    if out2 is not None:
                        print("Downloaded:", out2)
                        return 0

            # Periodic history poll (works even when updates don't contain media).
            now = asyncio.get_event_loop().time()
            if (now - last_history_check) >= poll_interval:
                last_history_check = now
                got_path, new_after = await _poll_history_once(after_id=start_id)
                start_id = int(new_after)
                if got_path is not None:
                    print("Downloaded:", got_path)
                    return 0
    finally:
        await client.close()

async def _cmd_promote(args: argparse.Namespace) -> int:
    from telecraft.client import ADMIN_RIGHTS_BASIC, ClientInit, MtprotoClient, make_admin_rights

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        channel_ref = _parse_peer_arg(args.channel)
        user_ref = _parse_peer_arg(args.user)

        if args.demote:
            rights = make_admin_rights()
            rank = ""
        elif args.full:
            rights = make_admin_rights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=True,
                manage_topics=True,
            )
            rank = args.rank or ""
        else:
            rights = ADMIN_RIGHTS_BASIC
            rank = args.rank or ""

        res = await client.edit_admin(
            channel_ref,
            user_ref,
            admin_rights=rights,
            rank=rank,
            timeout=args.timeout,
        )
        print(repr(res))
        return 0
    finally:
        await client.close()


async def _cmd_ban(args: argparse.Namespace) -> int:
    from telecraft.client import ClientInit, MtprotoClient, banned_rights_full_ban, make_banned_rights

    api_id = _need_env_int("TELEGRAM_API_ID")
    api_hash = _need_env("TELEGRAM_API_HASH")

    session = args.session or _pick_existing_session(args.network, args.dc)
    if not Path(session).exists():
        raise SystemExit(f"No session found. Run login first. Expected: {session}")
    dc, host, port, framing = _session_client_args(session)
    client = MtprotoClient(
        network=args.network,
        dc_id=dc,
        host=host,
        port=port,
        framing=framing,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect(timeout=args.timeout)
    try:
        channel_ref = _parse_peer_arg(args.channel)
        user_ref = _parse_peer_arg(args.user)

        if args.unban:
            rights = make_banned_rights(until_date=0)
        else:
            rights = banned_rights_full_ban(until_date=int(args.until))

        res = await client.edit_banned(
            channel_ref,
            user_ref,
            banned_rights=rights,
            timeout=args.timeout,
        )
        print(repr(res))
        return 0
    finally:
        await client.close()

def main() -> int:
    p = argparse.ArgumentParser(description="Telecraft simple runner")

    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--network", choices=["test", "prod"], default="prod")
        sp.add_argument("--dc", type=int, default=2)
        sp.add_argument("--framing", choices=["intermediate", "abridged"], default="intermediate")
        sp.add_argument("--timeout", type=float, default=30.0)
        sp.add_argument("--session", type=str, default=None)

    login = sub.add_parser("login", help="Login")
    add_common(login)
    login.add_argument("--phone", type=str, default=None)
    login.add_argument("--code", type=str, default=None)
    login.add_argument("--password", type=str, default=None)
    login.add_argument("--first-name", type=str, default=None)
    login.add_argument("--last-name", type=str, default=None)

    me = sub.add_parser("me", help="Print current user")
    add_common(me)

    s = sub.add_parser("send-self", help="Send a message to Saved Messages")
    add_common(s)
    s.add_argument("text", type=str)

    send = sub.add_parser("send", help="Send a message to a peer (resolve @username/+phone)")
    add_common(send)
    send.add_argument(
        "peer",
        type=str,
        help="Target: @username | +phone | user:ID | chat:ID | channel:ID",
    )
    send.add_argument("text", type=str)

    sf = sub.add_parser("send-file", help="Upload and send a local file (photo/document)")
    add_common(sf)
    sf.add_argument("peer", type=str, help="Target: @username | +phone | user:ID | chat:ID | channel:ID")
    sf.add_argument("path", type=str, help="Local file path")
    sf.add_argument("--caption", type=str, default=None)
    sf.add_argument("--as-photo", action="store_true", help="Force send as photo")
    sf.add_argument("--as-document", action="store_true", help="Force send as document")

    dl = sub.add_parser("download-next-media", help="Wait for next incoming media message and download it")
    add_common(dl)
    dl.add_argument("--dest", type=str, default="downloads/", help="Directory or file path")

    promote = sub.add_parser("promote", help="channels.editAdmin (promote/demote user in a channel)")
    add_common(promote)
    promote.add_argument("channel", type=str, help="Target channel: @username | channel:ID")
    promote.add_argument("user", type=str, help="Target user: @username | +phone | user:ID")
    promote.add_argument("--rank", type=str, default="", help="Admin rank label (optional)")
    promote.add_argument("--full", action="store_true", help="Grant a broad set of admin rights")
    promote.add_argument("--demote", action="store_true", help="Demote (remove admin rights)")

    ban = sub.add_parser("ban", help="channels.editBanned (ban/unban user in a channel)")
    add_common(ban)
    ban.add_argument("channel", type=str, help="Target channel: @username | channel:ID")
    ban.add_argument("user", type=str, help="Target user: @username | +phone | user:ID")
    ban.add_argument("--until", type=int, default=0, help="until_date (0=forever)")
    ban.add_argument("--unban", action="store_true", help="Unban/unrestrict (clear banned rights)")

    upd = sub.add_parser("updates", help="Print incoming updates")
    add_common(upd)

    args = p.parse_args()

    try:
        if args.cmd == "login":
            return asyncio.run(_cmd_login(args))
        if args.cmd == "me":
            return asyncio.run(_cmd_me(args))
        if args.cmd == "send-self":
            return asyncio.run(_cmd_send_self(args))
        if args.cmd == "send":
            return asyncio.run(_cmd_send(args))
        if args.cmd == "send-file":
            return asyncio.run(_cmd_send_file(args))
        if args.cmd == "download-next-media":
            return asyncio.run(_cmd_download_next_media(args))
        if args.cmd == "promote":
            return asyncio.run(_cmd_promote(args))
        if args.cmd == "ban":
            return asyncio.run(_cmd_ban(args))
        if args.cmd == "updates":
            return asyncio.run(_cmd_updates(args))
        raise SystemExit("unknown command")
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

