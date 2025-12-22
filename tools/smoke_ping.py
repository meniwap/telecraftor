from __future__ import annotations

import argparse
import asyncio
import logging
import secrets

from telecraft.mtproto.auth.handshake import exchange_auth_key
from telecraft.mtproto.auth.server_keys import DEFAULT_SERVER_KEYRING
from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.mtproto.rpc.sender import MtprotoEncryptedSender
from telecraft.mtproto.transport.abridged import AbridgedFraming
from telecraft.mtproto.transport.base import Endpoint
from telecraft.mtproto.transport.intermediate import IntermediateFraming
from telecraft.mtproto.transport.tcp import TcpTransport
from telecraft.tl.generated.functions import Ping

TEST_DCS: dict[int, tuple[str, int]] = {
    1: ("149.154.175.10", 443),
    2: ("149.154.167.40", 443),
    3: ("149.154.175.117", 443),
}


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.host is not None:
        host, port = args.host, args.port
    else:
        host, port = TEST_DCS[args.dc]

    framing = IntermediateFraming() if args.framing == "intermediate" else AbridgedFraming()
    transport = TcpTransport(endpoint=Endpoint(host=host, port=port), framing=framing)

    await transport.connect()
    try:
        rsa_keys = list(DEFAULT_SERVER_KEYRING.keys_by_fingerprint.values())
        res = await asyncio.wait_for(
            exchange_auth_key(transport, rsa_keys=rsa_keys),
            timeout=args.timeout,
        )

        msg_id_gen = MsgIdGenerator()
        state = MtprotoState(
            auth_key=res.auth_key,
            server_salt=res.server_salt,
            msg_id_gen=msg_id_gen,
        )
        sender = MtprotoEncryptedSender(transport, state=state, msg_id_gen=msg_id_gen)

        ping_id = secrets.randbits(63)
        pong = await sender.invoke_tl(Ping(ping_id=ping_id), timeout=args.timeout)
        print({"ping_id": ping_id, "pong": repr(pong)})
        return 0
    finally:
        await transport.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Smoke-test encrypted MTProto ping (auth_key + MTProto v2)."
    )
    p.add_argument(
        "--dc",
        type=int,
        choices=sorted(TEST_DCS.keys()),
        default=2,
        help="Test DC number",
    )
    p.add_argument("--host", type=str, default=None, help="Override host (disables --dc mapping)")
    p.add_argument("--port", type=int, default=443, help="Port (when using --host)")
    p.add_argument(
        "--framing",
        choices=["intermediate", "abridged"],
        default="intermediate",
        help="Transport framing mode",
    )
    p.add_argument("--timeout", type=float, default=20.0, help="Timeout (seconds)")
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

