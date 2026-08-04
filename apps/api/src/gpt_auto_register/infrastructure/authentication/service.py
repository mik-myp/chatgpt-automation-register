from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from gpt_auto_register.core.config import Settings
from gpt_auto_register.core.security import (
    csrf_token,
    hash_password,
    random_token,
    token_hash,
    verify_password,
)
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.auth import LoginAttempt, User, UserRole, UserSession

SESSION_COOKIE_NAME = "gpt_auto_session"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: UserSession
    raw_token: str
    csrf_token: str


class AuthenticationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: UserRole = UserRole.ADMIN,
    ) -> User:
        user = User(
            username=username.strip().lower(),
            password_hash=hash_password(password),
            role=role,
            password_changed_at=utc_now(),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def issue_session(
        self,
        user: User,
        *,
        client_address: str,
        user_agent: str,
    ) -> AuthenticatedSession:
        now = utc_now()
        raw_token = random_token()
        raw_csrf = csrf_token(raw_token)
        user_session = UserSession(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            csrf_token_hash=token_hash(raw_csrf),
            client_address=client_address[:64],
            user_agent=user_agent[:512],
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + timedelta(days=self.settings.session_idle_days),
            absolute_expires_at=now + timedelta(days=self.settings.session_absolute_days),
        )
        self.session.add(user_session)
        self.session.flush()
        return AuthenticatedSession(user, user_session, raw_token, raw_csrf)

    def authenticate(self, raw_token: str) -> AuthenticatedSession | None:
        now = utc_now()
        user_session = self.session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash(raw_token))
        )
        if (
            user_session is None
            or user_session.revoked_at is not None
            or _aware(user_session.idle_expires_at) <= now
            or _aware(user_session.absolute_expires_at) <= now
        ):
            return None
        user = self.session.get(User, user_session.user_id)
        if user is None or not user.active:
            return None
        raw_csrf = csrf_token(raw_token)
        if token_hash(raw_csrf) != user_session.csrf_token_hash:
            return None
        if _aware(user_session.last_seen_at) <= now - timedelta(minutes=5):
            user_session.last_seen_at = now
            user_session.idle_expires_at = min(
                now + timedelta(days=self.settings.session_idle_days),
                _aware(user_session.absolute_expires_at),
            )
            self.session.commit()
        return AuthenticatedSession(user, user_session, raw_token, raw_csrf)

    def login_allowed(self, username: str, client_address: str) -> bool:
        cutoff = utc_now() - timedelta(minutes=15)
        failures = self.session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.attempted_at >= cutoff,
                or_(
                    LoginAttempt.username == username,
                    LoginAttempt.client_address == client_address,
                ),
            )
        )
        return int(failures or 0) < 5

    def record_login(self, username: str, client_address: str, *, succeeded: bool) -> None:
        self.session.add(
            LoginAttempt(
                username=username,
                client_address=client_address[:64],
                succeeded=succeeded,
            )
        )
        self.session.commit()

    def verify_login(self, username: str, password: str) -> User | None:
        user = self.session.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None or not user.active or not verify_password(user.password_hash, password):
            return None
        return user

    def revoke(self, session_id: str) -> None:
        user_session = self.session.get(UserSession, session_id)
        if user_session is not None and user_session.revoked_at is None:
            user_session.revoked_at = utc_now()
            self.session.commit()

    def revoke_all(self, user_id: str) -> None:
        self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        self.session.commit()

    def change_password(self, user: User, current_password: str, new_password: str) -> bool:
        if not verify_password(user.password_hash, current_password):
            return False
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utc_now()
        self.revoke_all(user.id)
        return True
