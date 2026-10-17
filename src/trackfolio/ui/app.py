"""TrackFolio dashboard entry point."""

import plotly.express as px
import streamlit as st

from trackfolio.ui.common import initialize, service_context

st.set_page_config(page_title="TrackFolio", page_icon="📈", layout="wide")
initialize()

st.title("TrackFolio")
st.caption("Il tuo portafoglio, in locale.")

session, service = service_context()
try:
    history, holdings, metrics, warnings = service.dashboard_data()
finally:
    session.close()

for warning in warnings:
    st.warning(warning)

if history.empty:
    st.info("Aggiungi una transazione per iniziare a monitorare il portafoglio.")
else:
    first, second, third, fourth = st.columns(4)
    first.metric("Valore totale", f"€ {metrics.total_value:,.2f}")
    second.metric("Capitale investito", f"€ {metrics.invested_capital:,.2f}")
    third.metric("Profitto / perdita", f"€ {metrics.profit_loss:,.2f}")
    fourth.metric("Rendimento", f"{metrics.return_pct:,.2f}%")
    fifth, sixth, _, _ = st.columns(4)
    if metrics.twr_pct is not None:
        fifth.metric("Rendimento TWR", f"{metrics.twr_pct:,.2f}%")
    if metrics.xirr_pct is not None:
        sixth.metric("XIRR annualizzato", f"{metrics.xirr_pct:,.2f}%")

    chart_col, allocation_col = st.columns([2, 1])
    with chart_col:
        st.subheader("Valore del portafoglio")
        st.line_chart(
            history[["value", "invested_capital"]].rename(
                columns={"value": "Valore", "invested_capital": "Capitale investito"}
            )
        )
    with allocation_col:
        st.subheader("Allocazione")
        allocation = holdings[holdings["value_eur"] > 0]
        if not allocation.empty:
            figure = px.pie(
                allocation.reset_index(),
                values="value_eur",
                names="ticker",
                hole=0.35,
            )
            st.plotly_chart(figure, use_container_width=True)

    st.subheader("Posizioni")
    display = holdings.rename(
        columns={
            "name": "Titolo",
            "currency": "Valuta",
            "quantity": "Quantità",
            "average_cost": "PMC (valuta titolo)",
            "price": "Prezzo",
            "value": "Valore (valuta titolo)",
            "value_eur": "Valore (EUR)",
            "profit_loss": "P/L (valuta titolo)",
            "realized_pnl": "P/L realizzato (valuta titolo)",
            "dividends": "Dividendi netti (valuta titolo)",
        }
    )
    st.dataframe(display, use_container_width=True)
