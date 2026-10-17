# TrackFolio

TrackFolio è un'applicazione locale per registrare manualmente acquisti e vendite,
ricostruire le posizioni e visualizzare valore storico e rendimento del portafoglio.
I dati sono conservati in un database SQLite locale; le richieste esterne riguardano
solo ricerca dei titoli e dati di mercato.

## Requisiti

- Python 3.12 o superiore
- [uv](https://docs.astral.sh/uv/) per installazione e comandi riproducibili

## Avvio rapido

```powershell
uv sync --extra dev
uv run streamlit run src/trackfolio/ui/app.py
```

Apri l'indirizzo locale mostrato da Streamlit. La pagina **Transazioni** consente di
cercare uno strumento tramite ISIN o ticker, scegliere la quotazione e inserire,
modificare o eliminare le operazioni. La pagina **TrackFolio** mostra KPI, posizioni,
allocazione e storico. Il pulsante **Aggiorna prezzi** aggiorna la cache locale.

In alternativa, con un ambiente Python attivo:

```powershell
python -m pip install -e ".[dev]"
python -m streamlit run src/trackfolio/ui/app.py
```

## Test e qualità

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Dati e valute

Il database viene creato in `data/trackfolio.db`, escluso da Git. I prezzi giornalieri
provengono da Yahoo Finance e vengono memorizzati localmente. OpenFIGI è usato per
risolvere un ISIN; la ricerca Yahoo Finance è il fallback disponibile. I prezzi e il
capitale investito sono convertiti in EUR tramite cambi storici Yahoo Finance.

L'app non può aggiornare i prezzi se la fonte remota non è raggiungibile: in tal caso
mantiene la cache già salvata e segnala esplicitamente i ticker non disponibili. I
risultati dei provider gratuiti possono essere incompleti o in ritardo. Le posizioni
mostrano costo medio, prezzo e P/L non realizzato nella valuta dello strumento; i KPI
aggregati sono espressi in EUR.

## Struttura

- `src/trackfolio/core/`: calcoli puri di posizioni, serie storiche e KPI.
- `src/trackfolio/market_data/`: provider di mercato e ricerca ISIN/ticker.
- `src/trackfolio/repositories/`: persistenza SQLite.
- `src/trackfolio/services/`: orchestrazione delle operazioni applicative.
- `src/trackfolio/ui/`: interfaccia Streamlit.
- `tests/`: test unitari dei calcoli finanziari.

La roadmap e i requisiti funzionali sono definiti in
[.github/copilot-instructions.md](.github/copilot-instructions.md).
