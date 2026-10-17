"""Transaction entry, editing, and deletion."""

from datetime import date

import streamlit as st

from trackfolio.market_data.instrument_search import search_isin, search_ticker
from trackfolio.market_data.yfinance_provider import YFinanceProvider
from trackfolio.models import Asset, Transaction, TransactionType
from trackfolio.repositories.assets import get_asset
from trackfolio.ui.common import initialize, service_context

st.set_page_config(page_title="Transazioni | TrackFolio", layout="wide")
initialize()
st.title("Transazioni")

provider = YFinanceProvider()
with st.form("instrument_search"):
    search_value = st.text_input("ISIN o ticker/nome")
    search_kind = st.radio("Cerca per", ["Ticker o nome", "ISIN"], horizontal=True)
    search_clicked = st.form_submit_button("Cerca titolo")
if search_clicked:
    try:
        search_results = (
            search_isin(search_value, provider)
            if search_kind == "ISIN"
            else search_ticker(search_value, provider)
        )
        st.session_state["instrument_candidates"] = search_results
        st.session_state["instrument_search_error"] = None
        if not search_results:
            st.session_state["instrument_search_error"] = "Nessun titolo trovato."
    except (ValueError, RuntimeError) as error:
        st.session_state["instrument_candidates"] = []
        st.session_state["instrument_search_error"] = str(error)

if st.session_state.get("instrument_search_error"):
    st.warning(st.session_state["instrument_search_error"])

candidates: list[Asset] = st.session_state.get("instrument_candidates", [])
selected_asset: Asset | None
if candidates:
    selected_label = st.selectbox(
        "Quotazione",
        range(len(candidates)),
        format_func=lambda index: (
            f"{candidates[index].ticker} — {candidates[index].name} "
            f"({candidates[index].exchange or 'borsa n/d'}, {candidates[index].currency})"
        ),
    )
    selected_asset = candidates[selected_label]
else:
    selected_asset = None

session, service = service_context()
try:
    existing = service.list_transactions()
    currencies = service.asset_currencies()
    edit_id = st.selectbox(
        "Transazione da modificare o eliminare",
        [None, *[item.id for item in existing]],
        format_func=lambda value: (
            "Nuova transazione"
            if value is None
            else next(
                f"{item.date} · {item.type.value} {item.quantity:g} {item.ticker}"
                for item in existing
                if item.id == value
            )
        ),
    )
    current = next((item for item in existing if item.id == edit_id), None)
    edit_asset = get_asset(session, current.ticker) if current else None
    initial_asset = edit_asset if current else selected_asset

    with st.form("transaction_form"):
        row_one = st.columns(4)
        ticker = (
            row_one[0]
            .text_input(
                "Ticker",
                value=initial_asset.ticker
                if initial_asset
                else (current.ticker if current else ""),
            )
            .strip()
            .upper()
        )
        tx_date = row_one[1].date_input(
            "Data", value=current.date if current else date.today(), max_value=date.today()
        )
        tx_type = row_one[2].selectbox(
            "Tipo",
            [TransactionType.BUY, TransactionType.SELL],
            index=(
                [TransactionType.BUY, TransactionType.SELL].index(current.type) if current else 0
            ),
            format_func=lambda value: value.value,
        )
        asset_currency = (
            initial_asset.currency
            if initial_asset and initial_asset.ticker == ticker
            else currencies.get(ticker)
        )
        row_one[3].text_input("Valuta", value=asset_currency or "n/d", disabled=True)

        row_two = st.columns(4)
        quantity = row_two[0].number_input(
            "Quantità",
            min_value=0.000001,
            value=float(current.quantity) if current else 1.0,
            step=1.0,
            format="%.6f",
        )
        unit_price = row_two[1].number_input(
            "Prezzo unitario",
            min_value=0.0,
            value=float(current.price) if current else 0.0,
            step=0.01,
            format="%.4f",
        )
        fees = row_two[2].number_input(
            "Commissioni",
            min_value=0.0,
            value=float(current.fees) if current else 0.0,
            step=0.01,
            format="%.2f",
        )
        notes = row_two[3].text_input("Note", value=current.notes or "" if current else "")
        submitted = st.form_submit_button(
            "Salva modifiche" if current else "Aggiungi transazione",
            type="primary",
        )

        if submitted:
            try:
                transaction = Transaction(
                    id=current.id if current else None,
                    date=tx_date,
                    ticker=ticker,
                    type=tx_type,
                    quantity=quantity,
                    price=unit_price,
                    fees=fees,
                    notes=notes.strip() or None,
                )
                service.save_transaction(
                    transaction,
                    initial_asset if initial_asset and initial_asset.ticker == ticker else None,
                )
                st.success("Transazione salvata.")
                st.rerun()
            except (ValueError, RuntimeError) as error:
                st.error(str(error))

    if current and current.id is not None and st.button("Elimina transazione", type="secondary"):
        try:
            service.delete_transaction(current.id)
            st.success("Transazione eliminata.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    if existing:
        st.subheader("Storico")
        st.dataframe(
            [
                {
                    "ID": item.id,
                    "Data": item.date,
                    "Ticker": item.ticker,
                    "Tipo": item.type.value,
                    "Quantità": item.quantity,
                    "Prezzo": item.price,
                    "Commissioni": item.fees,
                    "Valuta": currencies.get(item.ticker),
                    "Note": item.notes,
                }
                for item in existing
            ],
            use_container_width=True,
            hide_index=True,
        )
finally:
    session.close()
