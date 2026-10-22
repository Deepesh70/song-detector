import time
import uuid
from typing import Optional
import jwt
from pydantic import BaseModel

DEFAULT_JWT_SECRET: str = "song-detector-fallback-secret-key-change-in-prod"
JWT_ALGORITHM: str = "HS256"
TOKEN_EXPIRY_SECONDS: int = 30
REDIS_NONCE_PREFIX: str = "fallback_nonce:"


class FallbackTokenPayload(BaseModel):
    jti: str
    exp: int
    iat: int


class FallbackManager:
    """Manages creation and atomic consumption of single-use fallback tokens using Redis."""

    def __init__(self, redis_client, secret_key: str = DEFAULT_JWT_SECRET):
        self.redis = redis_client
        self.secret_key = secret_key

    def create_fallback_token(self) -> str:
        """Create a signed JWT with a unique nonce (jti) and store it in Redis with 30s TTL."""
        nonce = str(uuid.uuid4())
        now = int(time.time())
        exp = now + TOKEN_EXPIRY_SECONDS

        payload = {
            "jti": nonce,
            "iat": now,
            "exp": exp,
        }

        token = jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)

        # Store in Redis with NX (set only if not exists) and EX (expire in seconds)
        redis_key = f"{REDIS_NONCE_PREFIX}{nonce}"
        self.redis.set(redis_key, "1", ex=TOKEN_EXPIRY_SECONDS)

        return token

    def verify_and_consume_token(self, token: str) -> bool:
        """Verify token signature and atomically delete the nonce via GETDEL to prevent replay attacks."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return False

        nonce = payload.get("jti")
        if not nonce:
            return False

        redis_key = f"{REDIS_NONCE_PREFIX}{nonce}"

        # Atomic retrieval and deletion to guarantee single-use consumption
        # redis-py supports getdel directly
        try:
            consumed = self.redis.getdel(redis_key)
            return consumed is not None
        except Exception:
            # Fallback for Redis engines without GETDEL command
            val = self.redis.get(redis_key)
            if val:
                self.redis.delete(redis_key)
                return True
            return False
