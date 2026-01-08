"""
Manual integration tests for telecraft.

These tests require:
1. A real Telegram account or test account
2. Environment variables set:
   - TELEGRAM_API_ID
   - TELEGRAM_API_HASH
   - TELEGRAM_PHONE (for login)
   - TELEGRAM_SESSION_PATH (optional, path to session file)

To run:
    TELEGRAM_API_ID=xxx TELEGRAM_API_HASH=yyy TELEGRAM_PHONE=+123... \
    pytest tests/test_integration_manual.py -v -s --run-integration

These tests are skipped by default to avoid requiring credentials in CI.
"""

from __future__ import annotations

import os

import pytest

# Skip all tests in this module unless explicitly enabled
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1",
    reason="Integration tests require RUN_INTEGRATION_TESTS=1 and credentials",
)


def get_test_config():
    """Get configuration from environment variables."""
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    phone = os.environ.get("TELEGRAM_PHONE")
    session_path = os.environ.get("TELEGRAM_SESSION_PATH", ".sessions/integration_test")

    if not api_id or not api_hash:
        pytest.skip("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")

    return {
        "api_id": int(api_id),
        "api_hash": api_hash,
        "phone": phone,
        "session_path": session_path,
    }


class TestConnectionIntegration:
    """Integration tests for basic connection and auth."""

    def test_connect_and_ping(self):
        """Test basic connection and ping to Telegram servers."""
        import asyncio

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                assert client.is_connected

                # Try a ping
                from telecraft.tl.generated.functions import Ping
                from secrets import randbits

                pong = await client.invoke_api(Ping(ping_id=randbits(63)), timeout=10.0)
                assert hasattr(pong, "TL_NAME")
                assert pong.TL_NAME == "pong"
            finally:
                await client.close()

        asyncio.run(run_test())


class TestLoginIntegration:
    """Integration tests for login flow."""

    def test_send_code(self):
        """Test sending login code (requires phone number)."""
        import asyncio

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()
        if not config["phone"]:
            pytest.skip("TELEGRAM_PHONE is required for login tests")

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                result = await client.send_code(config["phone"])
                # Result should have phone_code_hash
                assert hasattr(result, "phone_code_hash")
                print(f"Code sent! phone_code_hash={result.phone_code_hash[:10]}...")
            finally:
                await client.close()

        asyncio.run(run_test())


class TestGetMeIntegration:
    """Integration tests for get_me (requires logged-in session)."""

    def test_get_me(self):
        """Test getting current user info."""
        import asyncio

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                me = await client.get_me()
                if me is None:
                    pytest.skip("Not logged in (session may be expired)")
                print(f"Logged in as: {getattr(me, 'username', 'no username')}")
                print(f"User ID: {getattr(me, 'id', 'unknown')}")
            finally:
                await client.close()

        asyncio.run(run_test())


class TestMessagesIntegration:
    """Integration tests for sending/receiving messages."""

    def test_send_message_to_saved_messages(self):
        """Test sending a message to Saved Messages."""
        import asyncio
        from datetime import datetime

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                me = await client.get_me()
                if me is None:
                    pytest.skip("Not logged in")

                # Send to Saved Messages (self)
                test_msg = f"Integration test message at {datetime.utcnow().isoformat()}"
                result = await client.send_message_self(test_msg)
                assert result is not None
                print(f"Sent message: {test_msg}")
            finally:
                await client.close()

        asyncio.run(run_test())

    def test_iter_dialogs(self):
        """Test iterating over dialogs."""
        import asyncio

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                me = await client.get_me()
                if me is None:
                    pytest.skip("Not logged in")

                count = 0
                async for dialog in client.iter_dialogs(limit=5):
                    count += 1
                    peer = getattr(dialog, "peer", None)
                    print(f"Dialog {count}: {peer}")

                assert count > 0, "Expected at least one dialog"
                print(f"Total dialogs fetched: {count}")
            finally:
                await client.close()

        asyncio.run(run_test())


class TestMediaIntegration:
    """Integration tests for media upload/download."""

    def test_download_photo_from_saved_messages(self):
        """Test downloading a photo from Saved Messages."""
        import asyncio
        import tempfile
        from pathlib import Path

        from telecraft.client.mtproto import ClientInit, MtprotoClient

        config = get_test_config()

        async def run_test():
            client = MtprotoClient(
                network="production",
                dc_id=2,
                init=ClientInit(api_id=config["api_id"], api_hash=config["api_hash"]),
                session_path=config["session_path"],
            )
            try:
                await client.connect(timeout=30.0)
                me = await client.get_me()
                if me is None:
                    pytest.skip("Not logged in")

                # Get recent messages from Saved Messages
                found_photo = False
                async for msg in client.iter_messages(("user", me.id), limit=20):
                    media = getattr(msg, "media", None)
                    if media and getattr(media, "TL_NAME", None) == "messageMediaPhoto":
                        print(f"Found photo message: {msg.id}")
                        with tempfile.TemporaryDirectory() as tmpdir:
                            result = await client.download_media(msg, dest=tmpdir)
                            if result:
                                print(f"Downloaded to: {result}")
                                assert Path(result).exists()
                                assert Path(result).stat().st_size > 0
                                found_photo = True
                        break

                if not found_photo:
                    print("No photo found in recent Saved Messages")
                    # This is not a failure - just no photos available
            finally:
                await client.close()

        asyncio.run(run_test())
