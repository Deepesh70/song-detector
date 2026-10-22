import time
import fakeredis
from backend.fallback import FallbackManager


def test_fallback_token_lifecycle():
    """Verify single-use fallback token generation, consumption, and replay prevention."""
    server = fakeredis.FakeServer()
    r = fakeredis.FakeStrictRedis(server=server)
    manager = FallbackManager(redis_client=r, secret_key="test-secret-at-least-32-bytes-long-key-for-hmac-sha256")

    # Generate token
    token = manager.create_fallback_token()
    assert isinstance(token, str)

    # First consumption must succeed
    assert manager.verify_and_consume_token(token) is True

    # Immediate replay must fail because nonce was atomically deleted
    assert manager.verify_and_consume_token(token) is False


def test_fallback_token_tampering():
    """Verify tampered or invalid tokens are rejected."""
    r = fakeredis.FakeStrictRedis()
    manager = FallbackManager(redis_client=r, secret_key="test-secret-at-least-32-bytes-long-key-for-hmac-sha256")

    assert manager.verify_and_consume_token("invalid.jwt.token") is False
    assert manager.verify_and_consume_token("") is False
