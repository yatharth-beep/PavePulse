import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

PASSWORD_ITERATIONS = 310_000
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    expires_in = settings.jwt_expiry_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "iss": "pavepulse-api",
        "aud": "pavepulse-dashboard",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), expires_in


def _decode_local_token(token: str) -> dict[str, Any] | None:
    """Decode the legacy PavePulse API token used by local/test deployments."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="pavepulse-api",
            audience="pavepulse-dashboard",
            options={"require": ["sub", "exp", "iat", "iss", "aud", "ver"]},
        )
    except jwt.PyJWTError:
        return None


_supabase_jwks_client = None


def _decode_supabase_token(token: str) -> dict[str, Any] | None:
    """Verify a Supabase access token using the project's configured signing key/JWKS."""
    global _supabase_jwks_client
    if not settings.supabase_url:
        return None
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        options = {"require": ["sub", "exp", "iat", "iss", "aud"]}
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                return None
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                issuer=issuer,
                audience="authenticated",
                options=options,
            )
        if algorithm not in {"ES256", "RS256", "EdDSA"}:
            return None
        if _supabase_jwks_client is None:
            from jwt import PyJWKClient
            _supabase_jwks_client = PyJWKClient(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                timeout=5,
            )
        signing_key = _supabase_jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            issuer=issuer,
            audience="authenticated",
            options=options,
        )
    except (jwt.PyJWTError, ValueError, OSError, RuntimeError):
        return None


def _sync_supabase_user(payload: dict[str, Any], db: Session) -> User:
    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Supabase session has no verified email identity")

    configured_role = settings.supabase_role_by_email.get(email)
    app_metadata = payload.get("app_metadata") or {}
    trusted_role = app_metadata.get("role") if isinstance(app_metadata, dict) else None
    if trusted_role not in {"engineer", "worker"}:
        trusted_role = configured_role
    # A configured account's role cannot be overwritten by any conflicting claim.
    if configured_role and trusted_role and configured_role != trusted_role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account role configuration is inconsistent")
    role = configured_role or trusted_role
    if role not in {"engineer", "worker"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This Supabase account is not authorized for PavePulse. Ask an Engineer to configure its role.")

    username = email.split("@", 1)[0].strip().lower()
    if not username or len(username) > 80:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The account email cannot be mapped to a PavePulse username")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    created = False
    if user is None:
        # Supabase owns the real credentials. This salted random hash only satisfies the
        # operational User foreign keys; it cannot be used as the Supabase password.
        user = User(username=username, password_hash=hash_password(secrets.token_urlsafe(48)), role=role, is_active=True)
        db.add(user)
        db.flush()
        created = True
    elif user.role != role:
        user.role = role
        user.token_version += 1
        db.add(user)
    db.commit()
    db.refresh(user)
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This PavePulse account has been deactivated")
    if created:
        try:
            from app.services.audit import record_audit
            record_audit(
                db, actor=user, action="auth.supabase_user_mapped", entity_type="user", entity_id=str(user.id),
                details={"email": email, "role": role},
            )
        except Exception:
            db.rollback()
            # Account mapping should remain available even if initial audit initialization races.
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})

    token = credentials.credentials
    payload = _decode_local_token(token)
    if payload is not None:
        try:
            user_id = UUID(payload["sub"])
        except (ValueError, KeyError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token")
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is unavailable")
        if payload.get("ver") != user.token_version:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid; sign in again")
        return user

    supabase_payload = _decode_supabase_token(token)
    if supabase_payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    return _sync_supabase_user(supabase_payload, db)


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot perform this action")
        return user

    return dependency


def verify_device_key(key: str | None) -> bool:
    if not key:
        return False
    return hmac.compare_digest(key, settings.device_api_key)


def public_user(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "username": user.username, "role": user.role, "is_active": user.is_active}
