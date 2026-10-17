"""Transaction persistence helpers."""

from sqlmodel import Session, col, select

from trackfolio.models import Transaction


def list_transactions(session: Session) -> list[Transaction]:
    """Return transactions in chronological order."""
    statement = select(Transaction).order_by(col(Transaction.date), col(Transaction.id))
    return list(session.exec(statement).all())


def save_transaction(session: Session, transaction: Transaction) -> Transaction:
    """Insert or update a transaction."""
    transaction.ticker = transaction.ticker.upper()
    # merge: an edit arrives as a detached object whose row may already be loaded in the session
    saved = session.merge(transaction) if transaction.id is not None else transaction
    session.add(saved)
    session.flush()
    return saved


def delete_transaction(session: Session, transaction_id: int) -> None:
    """Delete a transaction by its identifier."""
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} does not exist")
    session.delete(transaction)
