"""Authentication: argon2 password hashing, user management and server-side sessions."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlmodel import Session, col, delete

from trackfolio.config import get_settings
from trackfolio.errors import DomainError, ErrorCode
from trackfolio.models import User, UserSession
from trackfolio.repositories import users
from trackfolio.services.rate_limiter import RateLimiter

LOGIN_KIND_PAIR = "login_fail_pair"  # same email from the same IP
LOGIN_KIND_IP = "login_fail_ip"
LOGIN_KIND_EMAIL = "login_fail_email"  # distributed guessing against one account
LOGIN_PAIR_LIMIT = 5
LOGIN_IP_LIMIT = 20
LOGIN_EMAIL_LIMIT = 30
LOGIN_WINDOW = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 12
UNUSABLE_HASH = "!"

_hasher = PasswordHasher()
# Verified when the email is unknown so that login time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def _now() -> datetime:
    return datetime.now(UTC)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class LoginResult:
    """Cookie token and lifetime of a new session."""

    token: str
    max_age_seconds: int


class AuthService:
    """User accounts and sessions; commits its own changes."""

    def __init__(self, session: Session, clock: Callable[[], datetime] = _now) -> None:
        self.session = session
        self.clock = clock  # used by the login rate limiter

    # -- user management (used by the admin CLI) --------------------------------------------

    def create_user(self, email: str, password: str, is_admin: bool = False) -> User:
        """Create an account with a hashed password."""
        email = users.normalize_email(email)
        self._check_email(email)
        self._check_password(password)
        if users.get_user_by_email(self.session, email):
            raise DomainError(ErrorCode.EMAIL_TAKEN, email=email)
        user = users.save_user(
            self.session,
            User(email=email, password_hash=_hasher.hash(password), is_admin=is_admin),
        )
        self.session.commit()
        return user

    def set_password(self, email: str, password: str) -> None:
        """Replace a password and end all of the user's sessions."""
        self._check_password(password)
        user = self._get(email)
        user.password_hash = _hasher.hash(password)
        users.save_user(self.session, user)
        self.session.exec(delete(UserSession).where(col(UserSession.user_id) == user.id))
        self.session.commit()

    def change_email(self, old: str, new: str) -> None:
        """Change a user's email."""
        new = users.normalize_email(new)
        self._check_email(new)
        user = self._get(old)
        if new != user.email and users.get_user_by_email(self.session, new):
            raise DomainError(ErrorCode.EMAIL_TAKEN, email=new)
        user.email = new
        users.save_user(self.session, user)
        self.session.commit()

    # -- login / sessions ---------------------------------------------------------------------

    def login(self, email: str, password: str, client_ip: str | None = None) -> LoginResult | None:
        """Check the credentials and open a session; None when they are wrong.

        Failed attempts are counted per (email, ``client_ip``), per IP and per email; when any
        is over its limit ``DomainError(RATE_LIMITED)`` is raised before any password hashing.
        The attempt is recorded before verifying and removed again on success. Check and record
        are separate steps, so a burst of truly parallel requests can overshoot a limit by the
        burst size; the limits are a brake, not an exact quota.
        """
        limiter = RateLimiter(self.session, self.clock)
        email_key = users.normalize_email(email)[:254]
        ip = client_ip or "-"
        buckets = [
            (LOGIN_KIND_PAIR, f"{ip}|{email_key}", LOGIN_PAIR_LIMIT),
            (LOGIN_KIND_IP, ip, LOGIN_IP_LIMIT),
            (LOGIN_KIND_EMAIL, email_key, LOGIN_EMAIL_LIMIT),
        ]
        waits = [limiter.check(kind, key, limit, LOGIN_WINDOW) for kind, key, limit in buckets]
        if wait := max(waits):
            raise DomainError(ErrorCode.RATE_LIMITED, seconds=wait)
        recorded = [limiter.record(kind, key) for kind, key, _ in buckets]
        user = users.get_user_by_email(self.session, email)
        if user is None or user.id is None or not self._verify(user, password):
            if user is None:
                self._verify_dummy(password)
            return None
        limiter.remove(recorded)
        settings = get_settings()
        lifetime = timedelta(days=settings.session_days)
        self.session.exec(delete(UserSession).where(col(UserSession.expires_at) < _now()))
        token = secrets.token_urlsafe(32)
        self.session.add(
            UserSession(
                token_hash=_token_hash(token),
                user_id=user.id,
                csrf_token=secrets.token_urlsafe(32),
                expires_at=_now() + lifetime,
            )
        )
        self.session.commit()
        return LoginResult(token, int(lifetime.total_seconds()))

    def resolve_session(self, token: str) -> tuple[User, UserSession] | None:
        """Return the user and session for a cookie token, or None if unknown or expired."""
        row = self.session.get(UserSession, _token_hash(token))
        if row is None:
            return None
        if row.expires_at < _now():
            self.session.delete(row)
            self.session.commit()
            return None
        user = users.get_user(self.session, row.user_id)
        return (user, row) if user else None

    def logout(self, token: str) -> None:
        """End the session of a cookie token."""
        row = self.session.get(UserSession, _token_hash(token))
        if row:
            self.session.delete(row)
            self.session.commit()

    # -- helpers ------------------------------------------------------------------------------

    def _get(self, email: str) -> User:
        user = users.get_user_by_email(self.session, email)
        if user is None:
            raise DomainError(ErrorCode.USER_NOT_FOUND, email=users.normalize_email(email))
        return user

    def _verify(self, user: User, password: str) -> bool:
        if user.password_hash == UNUSABLE_HASH:
            self._verify_dummy(password)
            return False
        try:
            _hasher.verify(user.password_hash, password)
        except InvalidHashError:
            self._verify_dummy(password)
            return False
        except VerificationError:
            return False
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
            users.save_user(self.session, user)
        return True

    @staticmethod
    def _verify_dummy(password: str) -> None:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass

    @staticmethod
    def _check_email(email: str) -> None:
        local, _, domain = email.partition("@")
        if not local or "." not in domain or " " in email:
            raise DomainError(ErrorCode.EMAIL_INVALID)

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise DomainError(ErrorCode.PASSWORD_TOO_SHORT, minimum=MIN_PASSWORD_LENGTH)
