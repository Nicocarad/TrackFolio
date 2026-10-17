# TrackFolio — Guida di progetto

> Documento di riferimento unico per requisiti, tecnologie e specifiche.
> Va aggiornato a ogni decisione rilevante. Se usato con Claude Code, può essere rinominato/copiato in `CLAUDE.md`.

**Stato:** Fase 1 — MVP locale implementato · **Versione doc:** 0.2

---

## 1. Visione

TrackFolio è un'applicazione per il tracking di un portafoglio di investimenti inserito **manualmente** dall'utente. A partire dalle transazioni registrate, ricostruisce la **serie storica del valore del portafoglio**, i guadagni/perdite e le principali statistiche finanziarie.

Principi guida:
- **Semplicità prima di tutto:** nessuna infrastruttura esterna (no server DB, no Docker, no cloud) nell'MVP.
- **Locale e privato:** i dati dell'utente restano in locale (SQLite).
- **Logica separata dalla UI:** il calcolo finanziario è una libreria Python pura, testabile, riusabile con qualsiasi frontend futuro.
- **Incrementale:** MVP minimo, poi feature a strati.

---

## 2. Scope

### 2.1 MVP (Fase 1) — IN scope
1. Inserimento manuale di transazioni (acquisto/vendita di titoli), con **ricerca del titolo per ISIN** o ticker.
2. Modifica e cancellazione delle transazioni.
3. Recupero automatico dei prezzi storici da fonte online (cache locale).
4. Calcolo e visualizzazione di:
   - composizione attuale del portafoglio (posizioni, quantità, prezzo medio di carico, valore, P&L);
   - serie storica del valore del portafoglio vs capitale versato;
   - guadagno/perdita totale (assoluto e %).
5. Persistenza locale dei dati.

### 2.2 Fuori scope nell'MVP (roadmap, vedi §10)
Dividendi/cedole, benchmark, statistiche di rischio avanzate, import CSV, multi-portafoglio, fiscalità, ribilanciamento, autenticazione/multiutente, deploy web, app mobile.

---

## 3. Requisiti funzionali (MVP)

| ID | Requisito | Priorità |
|----|-----------|----------|
| F1 | L'utente può aggiungere una transazione: data, ticker, tipo (BUY/SELL), quantità, prezzo unitario, commissioni, valuta, note | Must |
| F2 | L'utente può modificare/eliminare una transazione esistente | Must |
| F3 | Validazione input: ticker esistente, quantità > 0, prezzo ≥ 0, data non futura, impossibile vendere più di quanto posseduto alla data | Must |
| F4 | Il sistema scarica e salva in cache i prezzi giornalieri storici dei ticker in portafoglio | Must |
| F5 | Tabella posizioni correnti: ticker, quantità, PMC (prezzo medio di carico), prezzo attuale, valore, P&L assoluto e % | Must |
| F6 | Grafico serie storica: valore del portafoglio nel tempo + linea del capitale netto investito | Must |
| F7 | KPI di riepilogo: valore totale, capitale investito, P&L totale, rendimento % | Must |
| F8 | Grafico allocazione per titolo (peso % sul valore) | Should |
| F9 | Refresh manuale dei prezzi | Should |
| F10 | Gestione valute: conversione in valuta base (EUR) con cambi storici | Should |
| F11 | Ricerca titolo per **ISIN**: l'utente inserisce l'ISIN (validato con formato + check digit) e il sistema propone le quotazioni disponibili (borsa, ticker, valuta) tra cui scegliere | Must |
| F12 | Ricerca titolo per ticker (inserimento diretto, formato provider); l'ISIN viene salvato sull'asset quando noto | Must |

## 4. Requisiti non funzionali

- **Piattaforma:** esecuzione locale, cross-platform (Windows/macOS/Linux).
- **Performance:** ricalcolo serie storica < 2 s per portafoglio fino a ~50 titoli / 1000 transazioni (grazie a cache prezzi e calcolo vettoriale con pandas).
- **Affidabilità:** se la fonte prezzi non risponde, l'app usa la cache e segnala chiaramente i dati non aggiornati.
- **Correttezza:** logica finanziaria coperta da test unitari con casi calcolati a mano.
- **Manutenibilità:** type hints ovunque, linting automatico, moduli a responsabilità singola.
- **Privacy:** nessun dato personale inviato a terzi (solo richieste di prezzi per ticker).

---

## 5. Stack tecnologico

| Area | Scelta | Motivazione | Alternative |
|------|--------|-------------|-------------|
| Linguaggio | **Python 3.12+** | Ecosistema dati/finanza maturo | — |
| Gestione env | **uv** (o `venv` + pip) | Veloce, un solo `pyproject.toml` | Poetry |
| Dati / calcolo | **pandas + numpy** | Serie storiche, forward-fill, operazioni vettoriali | Polars |
| Finanza | **scipy** (XIRR/ottimizzazione), numpy | Rendimenti money-weighted | — |
| Risoluzione ISIN → ticker | **OpenFIGI API** (primaria) + `yfinance.Search` (fallback) | OpenFIGI è gratuita (con API key gratuita limiti più alti) e restituisce tutte le quotazioni per un ISIN; yfinance fornisce il ticker nel formato usato per i prezzi | Solo yfinance, mapping CSV locale |
| Validazione ISIN | **`python-stdnum`** (o check digit Luhn implementato in `core/`) | Verifica formato e cifra di controllo prima di chiamare servizi esterni | Regex + Luhn manuale |
| Prezzi di mercato | **yfinance** | Gratuito, copre azioni/ETF/FX/crypto | Stooq (via `pandas-datareader`), Alpha Vantage, EOD Historical Data |
| Database | **SQLite** | Zero configurazione, file singolo | PostgreSQL (solo se serve multiutente) |
| ORM / modelli | **SQLModel** (o SQLAlchemy 2.0 + Pydantic) | Modelli tipizzati + validazione | `sqlite3` puro |
| UI (MVP) | **Streamlit** | Sviluppo rapidissimo, ottimo per dashboard | Gradio, NiceGUI, Dash |
| Grafici | **Plotly** | Interattivi, ottima resa su serie storiche | Altair, Matplotlib |
| Test | **pytest** | Standard de facto | — |
| Qualità codice | **ruff** (lint + format) + **mypy** | Un tool veloce per lint/format; type checking | black + flake8 |
| Task runner | `Makefile` o `uv run` scripts | Comandi ripetibili | `just` |

**Evoluzione prevista:** se in futuro serve un frontend più ricco, il `core` resta invariato e si aggiunge un backend **FastAPI** + frontend dedicato (es. React). Per questo la UI non deve contenere logica di business.

### Setup VS Code consigliato
Estensioni: *Python*, *Pylance*, *Ruff*, *Jupyter* (per esplorazione), *SQLite Viewer*. Interprete: `.venv` del progetto.

---

## 6. Architettura

Tre livelli con dipendenze unidirezionali: `ui → services → core/data`.

```
trackfolio/
├── PROJECT_GUIDE.md
├── README.md
├── pyproject.toml
├── .gitignore                  # include data/*.db, .venv, .cache
├── data/                       # DB SQLite locale (non versionato)
├── src/trackfolio/
│   ├── config.py               # valuta base, path DB, parametri
│   ├── models.py               # Asset, Transaction, Price (SQLModel)
│   ├── db.py                   # engine, sessione, init schema
│   ├── repositories/           # CRUD su transazioni, asset, prezzi
│   ├── market_data/
│   │   ├── provider.py         # interfaccia astratta PriceProvider
│   │   ├── yfinance_provider.py
│   │   └── instrument_search.py  # ricerca per ISIN/ticker → lista quotazioni (OpenFIGI + yfinance)
│   ├── core/                   # LOGICA PURA, nessun I/O
│   │   ├── positions.py        # quantità e PMC nel tempo
│   │   ├── timeseries.py       # serie storica valore portafoglio
│   │   └── metrics.py          # P&L, rendimenti, (poi) rischio
│   ├── services/
│   │   └── portfolio_service.py  # orchestrazione: DB + prezzi + core
│   └── ui/
│       ├── app.py              # entry point Streamlit
│       └── pages/              # Transazioni, Dashboard
└── tests/
    ├── test_positions.py
    ├── test_timeseries.py
    └── test_metrics.py
```

Regole:
- `core/` riceve e restituisce solo DataFrame/dataclass: niente DB, niente rete, niente Streamlit.
- Il provider prezzi è dietro un'interfaccia (`PriceProvider`) per poter cambiare fonte senza toccare il resto.
- La UI chiama solo `services/`.

---

## 7. Modello dati (MVP)

**asset**
| campo | tipo | note |
|-------|------|------|
| ticker (PK) | str | formato provider, es. `VWCE.DE`, `AAPL` |
| isin | str, opz., indicizzato | 12 caratteri; lo stesso ISIN può comparire su più asset (una riga per quotazione/borsa) |
| exchange | str, opz. | borsa di quotazione, utile a distinguere le quotazioni dello stesso ISIN |
| name | str | |
| currency | str | valuta di quotazione (ISO) |
| asset_class | str, opz. | azione, ETF, obbligazione, crypto… |

**transaction**
| campo | tipo | note |
|-------|------|------|
| id (PK) | int | |
| date | date | data operazione |
| ticker (FK) | str | |
| type | enum | `BUY` / `SELL` |
| quantity | Decimal/float | > 0 |
| price | float | prezzo unitario in valuta dell'asset |
| fees | float | commissioni, default 0 |
| currency | str | valuta dell'operazione |
| notes | str, opz. | |

**price** (cache)
| campo | tipo | note |
|-------|------|------|
| ticker, date (PK composta) | | |
| close | float | |
| source | str | |
| fetched_at | datetime | per decidere il refresh |

Le serie FX (es. `EURUSD=X`) sono salvate nella stessa tabella `price` con il ticker del cambio.

---

## 8. Logica di calcolo (specifica)

**Posizioni**
- Quantità per ticker a data *t* = Σ BUY − Σ SELL fino a *t*.
- **PMC** (costo medio ponderato): BUY → `(q_old·pmc_old + q·p + fees)/(q_old+q)`; SELL → PMC invariato, riduce la quantità.
- P&L non realizzato = `qty · prezzo_attuale − qty · PMC`.
- P&L realizzato (SELL) = `q_venduta · (prezzo_vendita − PMC) − fees`.

**Serie storica**
1. Indice giornaliero dal giorno della prima transazione a oggi (calendario dei giorni di mercato o giorni solari con forward-fill dei prezzi).
2. Matrice quantità `[data × ticker]` ottenuta dal cumulato delle transazioni.
3. Matrice prezzi `[data × ticker]` con forward-fill; conversione in EUR con FX storico.
4. `valore(t) = Σ qty_i(t) · prezzo_i(t) · fx_i(t)`.
5. `capitale_netto_investito(t)` = cumulato di (acquisti + fee − vendite).
6. `P&L(t) = valore(t) − capitale_netto_investito(t)`.

**Metriche MVP:** valore totale, capitale investito, P&L assoluto, rendimento % semplice.
**Metriche Fase 2:** TWR, XIRR (money-weighted), CAGR; Fase 3: volatilità annualizzata, max drawdown, Sharpe/Sortino, beta vs benchmark, correlazioni.

---

## 9. Interfaccia (MVP)

Streamlit multipagina:
1. **Transazioni:** form di inserimento (con validazione) + tabella editabile/eliminabile. Il campo titolo accetta ISIN o ticker: con un ISIN valido compare un selettore delle quotazioni trovate (ticker, borsa, valuta) e la scelta compila automaticamente ticker e valuta.
2. **Dashboard:** KPI in alto, grafico serie storica (valore vs capitale investito), tabella posizioni, grafico allocazione.

Sidebar: pulsante "Aggiorna prezzi", indicatore data ultimo aggiornamento.

---

## 10. Roadmap

| Fase | Contenuto |
|------|-----------|
| **1 — MVP** | Inserimento transazioni, prezzi con cache, posizioni, serie storica, KPI base |
| **2 — Rendimenti** | Dividendi/cedole, TWR, XIRR, CAGR, rendimenti per periodo (YTD, 1Y, 3Y), P&L realizzato/non |
| **3 — Rischio e confronto** | Benchmark (es. MSCI World), volatilità, drawdown, Sharpe, correlazioni, ripartizione per asset class/area/valuta |
| **4 — Comodità** | Import/export CSV (anche da broker, con risoluzione ISIN), multi-portafoglio, ricerca per nome del titolo |
| **5 — Avanzate** | Fiscalità (plusvalenze, bollo), ribilanciamento verso allocazione target, alert, scenari/simulazioni |
| **6 — Distribuzione** | Backend FastAPI, eventuale frontend web, autenticazione, deploy |

---

## 11. Convenzioni di sviluppo

- **Stile:** ruff (format + lint), type hints obbligatori, docstring brevi sulle funzioni pubbliche.
- **Git:** branch `main` stabile, feature branch `feat/<nome>`, commit in formato Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`).
- **Test:** ogni funzione in `core/` ha almeno un test con valori calcolati a mano; i provider di rete vanno mockati.
- **Dati:** nessun DB o credenziale nel repository.
- **Denaro:** usare `float` nell'MVP, ma centralizzare gli arrotondamenti; valutare `Decimal` se emergono errori di precisione.

## 12. Comandi (da completare a setup fatto)

```bash
uv sync                              # installa dipendenze
uv run streamlit run src/trackfolio/ui/app.py
uv run pytest
uv run ruff check . && uv run ruff format .
```

## 13. Decisioni aperte e limiti noti

- **Valuta base:** EUR; prezzi e flussi in valute estere sono convertiti con cambi storici Yahoo Finance.
- **Stock split:** i prezzi storici di yfinance sono rettificati per gli split, quindi le quantità inserite prima di uno split vanno rettificate. Nell'MVP è un limite noto; da gestire con un tipo di evento `SPLIT`.
- **Dividendi:** esclusi dall'MVP, quindi il rendimento è calcolato sul solo prezzo (total return sottostimato per titoli a distribuzione).
- **ISIN → quotazione:** un ISIN identifica lo strumento, non la quotazione. Lo stesso ETF può essere quotato su più borse e valute, quindi la scelta della quotazione spetta all'utente; il sistema non la sceglie in automatico.
- **Copertura ticker:** i prezzi usano i ticker di Yahoo Finance (suffissi di borsa, es. `.MI`, `.DE`). Non tutti gli ISIN restituiti da OpenFIGI hanno un ticker corrispondente su Yahoo: in quel caso si mostra un avviso e si permette l'inserimento manuale del ticker.
- **Rate limit OpenFIGI:** il risultato della ricerca va salvato in cache (tabella `asset`) per non ripetere la chiamata.
- **Affidabilità fonte dati:** yfinance non è un'API ufficiale; mantenere il provider dietro interfaccia per poterlo sostituire.
- **Granularità:** prezzi giornalieri di chiusura (nessun intraday).

## 14. Definition of Done — MVP

- [ ] Posso inserire, modificare ed eliminare transazioni con validazione.
- [ ] Inserendo un ISIN valido ottengo le quotazioni disponibili e posso selezionarne una; un ISIN con check digit errato viene rifiutato.
- [ ] I prezzi vengono scaricati, salvati e riutilizzati da cache.
- [ ] La dashboard mostra posizioni, KPI e serie storica corretti su un portafoglio di prova verificato a mano.
- [x] Test sul `core` passano; ruff e mypy senza errori.
- [x] README con istruzioni di avvio.
