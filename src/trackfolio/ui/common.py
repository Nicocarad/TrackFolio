"""Shared Streamlit setup."""

import streamlit as st
from sqlmodel import Session

from trackfolio.db import get_session, init_db
from trackfolio.market_data.yfinance_provider import YFinanceProvider
from trackfolio.repositories.prices import latest_price_date
from trackfolio.services.portfolio_service import PortfolioService


def initialize() -> None:
    """Initialize schema and show shared market-data controls."""
    init_db()
    with st.sidebar:
        st.caption("Dati salvati solo in locale")
        with get_session() as session:
            last_updated = latest_price_date(session)
        st.caption(f"Ultimo prezzo in cache: {last_updated or 'mai'}")
        if st.button("Aggiorna prezzi", use_container_width=True):
            with get_session() as session:
                count, errors = PortfolioService(session, YFinanceProvider()).refresh_prices()
            if errors:
                for error in errors:
                    st.warning(error)
            else:
                st.success(f"Aggiornati {count} prezzi giornalieri.")
            st.rerun()


def service_context() -> tuple[Session, PortfolioService]:
    """Return a session and service; callers must close the session."""
    session = get_session()
    return session, PortfolioService(session, YFinanceProvider())
