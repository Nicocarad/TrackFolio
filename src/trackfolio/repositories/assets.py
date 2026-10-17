"""Asset persistence helpers."""

from sqlmodel import Session, select

from trackfolio.models import Asset


def get_asset(session: Session, ticker: str) -> Asset | None:
    """Return an asset by provider ticker."""
    return session.get(Asset, ticker.upper())


def get_assets(session: Session) -> list[Asset]:
    """Return all known assets ordered by ticker."""
    return list(session.exec(select(Asset).order_by(Asset.ticker)).all())


def save_asset(session: Session, asset: Asset) -> Asset:
    """Insert or update an asset."""
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset
