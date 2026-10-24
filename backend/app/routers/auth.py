from collections import defaultdict, deque
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import ChangePasswordIn, CreateUserIn, LoginIn, UserOut
from app.services.audit import record_audit
from app.services.auth import create_access_token, get_current_user, hash_password, public_user, require_roles, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = monotonic()
    attempts = _login_failures[client]
    while attempts and now - attempts[0] > 60:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many sign-in attempts. Wait one minute and retry.")


@router.post("/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    _rate_limit(request)
    username = payload.username.strip()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.is_active or user.role not in {"engineer", "worker"} or not verify_password(payload.password, user.password_hash):
        client = request.client.host if request.client else "unknown"
        _login_failures[client].append(monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    _login_failures.pop(request.client.host if request.client else "unknown", None)
    token, expires_in = create_access_token(user)
    record_audit(db, actor=user, action="auth.login", entity_type="user", entity_id=str(user.id), details={"success": True})
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": public_user(user)}


@router.post("/change-password")
def change_password(payload: ChangePasswordIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, actor.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if verify_password(payload.new_password, actor.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password must be different")
    actor.password_hash = hash_password(payload.new_password)
    actor.token_version += 1
    db.add(actor)
    record_audit(db, actor=actor, action="auth.password_changed", entity_type="user", entity_id=str(actor.id),
                 details={"username": actor.username}, commit=False)
    db.commit()
    token, expires_in = create_access_token(actor)
    return {"ok": True, "message": "Password updated", "access_token": token, "token_type": "bearer", "expires_in": expires_in}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    return db.execute(select(User).where(User.role.in_(["engineer", "worker"])).order_by(User.role, User.username)).scalars().all()


@router.get("/workers", response_model=list[UserOut])
def list_workers(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    return db.execute(select(User).where(User.role == "worker", User.is_active.is_(True)).order_by(User.username)).scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: CreateUserIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("engineer"))):
    if db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none():
        raise HTTPException(409, "Username already exists")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.flush()
    record_audit(db, actor=actor, action="auth.user_created", entity_type="user", entity_id=str(user.id),
                 details={"username": user.username, "role": user.role}, commit=False)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_user_active(
    user_id: UUID,
    is_active: bool,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    target = db.get(User, user_id)
    if not target or target.role not in {"engineer", "worker"}:
        raise HTTPException(404, "User not found")
    if target.id == actor.id and not is_active:
        raise HTTPException(422, "You cannot deactivate your own account")
    if target.is_active != is_active:
        previous = target.is_active
        target.is_active = is_active
        target.token_version += 1
        db.add(target)
        record_audit(db, actor=actor, action="auth.user_status_changed", entity_type="user", entity_id=str(target.id),
                     details={"username": target.username, "from": previous, "to": is_active}, commit=False)
        db.commit()
        db.refresh(target)
    return target
