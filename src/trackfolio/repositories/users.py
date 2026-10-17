"""User persistence helpers."""

from sqlmodel import Session, col, select

from trackfolio.models import User


def normalize_email(email: str) -> str:
    """Emails are matched case-insensitively and without surrounding spaces."""
    return email.strip().lower()


def get_user(session: Session, user_id: int) -> User | None:
    """Return a user by id."""
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return a user by email."""
    statement = select(User).where(User.email == normalize_email(email))
    return session.exec(statement).first()


def list_users(session: Session) -> list[User]:
    """Return all users ordered by id."""
    return list(session.exec(select(User).order_by(col(User.id))).all())


def save_user(session: Session, user: User) -> User:
    """Insert or update a user (the caller commits)."""
    user.email = normalize_email(user.email)
    session.add(user)
    session.flush()
    return user
