"""Transaction persistence helpers."""

from sqlmodel import Session, select

from trackfolio.models import Transaction


def list_transactions(session: Session) -> list[Transaction]:
    """Return transactions in chronological order."""
    statement = select(Transaction).order_by("date", "id")
    return list(session.exec(statement).all())


def save_transaction(session: Session, transaction: Transaction) -> Transaction:
    """Insert or update a transaction."""
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def delete_transaction(session: Session, transaction_id: int) -> None:
    """Delete a transaction by its identifier."""
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} does not exist")
    session.delete(transaction)
    session.commit()
