"""Transaction persistence helpers; every query is scoped to one user."""

from sqlmodel import Session, col, select

from trackfolio.errors import DomainError, ErrorCode
from trackfolio.models import Transaction


def list_transactions(session: Session, user_id: int) -> list[Transaction]:
    """Return the user's transactions in chronological order."""
    statement = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(col(Transaction.date), col(Transaction.id))
    )
    return list(session.exec(statement).all())


def list_all_transactions(session: Session) -> list[Transaction]:
    """Return every user's transactions (shared jobs only, never for request handling)."""
    return list(session.exec(select(Transaction).order_by(col(Transaction.id))).all())


def get_transaction(session: Session, user_id: int, transaction_id: int) -> Transaction:
    """Return one of the user's transactions; other users' rows look like missing ones."""
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user_id:
        raise DomainError(ErrorCode.TRANSACTION_NOT_FOUND, transaction_id=transaction_id)
    return transaction


def save_transaction(session: Session, user_id: int, transaction: Transaction) -> Transaction:
    """Insert or update a transaction owned by ``user_id``."""
    transaction.ticker = transaction.ticker.upper()
    transaction.user_id = user_id
    if transaction.id is not None:
        get_transaction(session, user_id, transaction.id)  # must exist and be the user's
    # merge: an edit arrives as a detached object whose row may already be loaded in the session
    saved = session.merge(transaction) if transaction.id is not None else transaction
    session.add(saved)
    session.flush()
    return saved


def delete_transaction(session: Session, user_id: int, transaction_id: int) -> None:
    """Delete one of the user's transactions."""
    session.delete(get_transaction(session, user_id, transaction_id))
