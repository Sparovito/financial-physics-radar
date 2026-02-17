# Financial Physics Market Radar — ARCHITECTURE

## 1. Overview

Financial Physics Market Radar è uno strumento di analisi finanziaria che applica concetti di fisica
(Principio di Minima Azione, energia cinetica/potenziale, analisi spettrale) per:

- visualizzare lo “stato energetico” del mercato (Overheating, Volatility, Equilibrium, Accumulation),
- confrontare strumenti tramite z-score su una canvas comune,
- generare proiezioni tramite Fourier / analisi spettrale,
- esplorare lo storico con una sorta di “time travel” dei pattern di mercato.

L’app è composta da:

- **Backend**: API FastAPI in Python che calcola tutti i dati (feature engineering, energie, score, forecast).
- **Frontend**: pagina HTML/JS statica servita dal backend, che usa Plotly.js per le visualizzazioni interattive.

## 2. High-level structure

Root:

- `backend/` — applicazione FastAPI
- `frontend/` — asset statici (HTML, JS, CSS, Plotly)
- `requirements.txt` — dipendenze Python
- `Procfile` — comando di start per Railway / produzione
- `*.ipynb` — notebook di ricerca/sperimentazione
- `setup_env.sh`, `start_app.sh` — script di utilità per ambiente locale

### 2.1 Backend (FastAPI)

`backend/` contiene:

- `main.py` (o equivalente):

  - crea l’istanza `FastAPI()`,
  - definisce o include le route principali (es. `/`, `/api/radar`, `/api/assets`, `/api/forecast`, ecc.),
  - monta la cartella `frontend/` come static files e/o template root.
- Moduli tipici (nomi da adattare alla struttura reale del repo):

  - `data_fetcher.py` / `services/data_sources.py`:
    - uso di yfinance o altre fonti per scaricare prezzi storici e volumi,
    - gestione della frequenza (daily, intraday, ecc.), dell’orizzonte temporale e del caching (se presente).
  - `physics_engine.py` / `services/physics_metrics.py`:
    - calcolo di energia cinetica/potenziale,
    - principio di minima azione / path energy,
    - stato del mercato (Overheating, Volatility, Equilibrium, Accumulation).
  - `zscore_utils.py`:
    - normalizzazione, z-score, comparazione cross-asset.
  - `fourier_forecast.py`:
    - analisi spettrale, ricostruzione serie, eventuali forecast.
  - `models.py` / `schemas.py`:
    - definizione di Pydantic models per request/response delle API (es. `AssetRequest`, `RadarPoint`, `ForecastResponse`).
- **Indicatori Stabili (Causali)** — calcolati in `main.py` endpoint `/analyze`:
  - Stable Kinetic Z: EMA(20) forward-only → Z-Score → hysteresis ±0.5.
  - Stable Slope: slope causale stabilizzata.
  - Regime array (+1/-1/0): input per `backtest_strategy()` con threshold=0.5.
  - Proprietà: valori passati **immutabili** (max_diff = 0.0 aggiungendo dati).

- **Email Alert STABLE** — `stable_scanner.py`:
  - Modulo dedicato per email giornaliere con segnali della strategia STABLE.
  - `download_all_prices()`: riutilizza `PRICE_CACHE`, `TICKER_CACHE` e `MarketData` da `main.py` (stessa infrastruttura di download, no `yf.download` separato).
  - `compute_stable_signals()`: auto-calcola finestra 6 mesi, download parallelo (ThreadPoolExecutor 8 workers), poi computazione segnali parallela.
  - `build_stable_email()`: genera HTML con 3 sezioni: ENTRY OGGI (verde), INGRESSI RECENTI <5gg (giallo/arancione con badge giorni), POSIZIONI ATTIVE (viola).
  - Config persistente in `stable_alert_config.json`.
  - `run_stable_scan()`: entry point principale, invocato dallo scheduler o dagli endpoint API.

- **Scheduler STABLE** — in `main.py`:
  - `_init_stable_scheduler()`: configura job APScheduler con `CronTrigger(hour, minute, timezone="Europe/Rome")`.
  - 5 endpoint dedicati:
    - `GET /stable-alert/config` — ritorna config + next_run_time scheduler.
    - `POST /stable-alert/config` — salva config, re-inizializza scheduler.
    - `POST /stable-alert/trigger` — background task (fire-and-forget).
    - `POST /stable-alert/test` — sincrono, ritorna risultati senza inviare email.
    - `POST /stable-alert/trigger-with-result` — sincrono, invia email E ritorna risultati per preview UI.

- **Sistema di Cache Prezzi** (condiviso tra moduli):
  - `PRICE_CACHE`: dict `{ticker|start_date: pd.Series}`, thread-safe con `_price_cache_lock`.
  - `TICKER_CACHE`: cache per-ticker con dati completi dall'analisi principale.
  - `stable_scanner.py` verifica prima `PRICE_CACHE` → poi `TICKER_CACHE` → poi `MarketData.fetch()`.
  - La cache viene invalidata per i ticker del portafoglio prima della scansione email (dati freschi per HOLD/SELL).

- **NotificationManager** — `notifications.py`:
  - Dual send: Resend API (prioritario, cloud) / SMTP fallback (locale).
  - Credenziali via env vars: `RESEND_API_KEY`, `EMAIL_SENDER`, `EMAIL_RECIPIENT`.

- Concetti chiave:

  - **Contracts API**: gli schemi Pydantic esposti dalle route sono considerati **contratti stabili**.
  - Il backend genera dati in un formato già pronto per il frontend (strutture JSON per Plotly e UI radar).

### 2.2 Frontend (HTML + JS + Plotly)

`frontend/` contiene:

- `index.html`:

  - layout di base dell’app,
  - container per i grafici (radar plot, timeline, heatmap, ecc.),
  - referenze ai bundle JS/CSS.
- `app.js` (o file similare):

  - chiama le API del backend (es. `/api/radar`, `/api/forecast`, ecc.),
  - trasforma le risposte JSON in figure Plotly,
  - gestisce interazioni tipo:
    - selezione di asset (ticker, lista, set predefiniti),
    - selezione orizzonte temporale e finestre di analisi,
    - time travel / slider temporale,
    - highlight di stati energetici (Overheating, Volatility, ecc.).
- `styles.css`:

  - styling base della UI (layout, colori, tipografia).

- `test_stable.html` + `test_stable.js` — **STABLE Strategy Lab**:

  - pagina dedicata alla strategia STABLE, separata dalla dashboard principale.
  - **Tab Analisi**: analisi singolo ticker con parametri STABLE (mode, entry, exit, alpha).
  - **Tab Batch**: analisi massiva di tutti i ticker con classifica e statistiche.
  - **Tab Optimizer**: grid search su parametri alpha per trovare configurazione ottimale.
  - **Tab 📩 Email Alert**: configurazione email giornaliere STABLE con toggle ON/OFF, orario trigger, parametri strategia, preset ticker, preview risultati.

### 2.3 Notebook e ricerca

- `FinancialPhysicsTool.ipynb` e altri notebook:
  - usati per esplorazione concettuale, prototipazione delle formule, test sui dati,
  - **non** fanno parte del path di esecuzione dell’app in produzione.

Le idee e le formule consolidate dai notebook dovrebbero essere estratte nei moduli Python del backend
(`physics_engine`, `fourier_forecast`, ecc.).

## 3. Flussi principali

### 3.1 Radar view

1. Frontend invia richiesta al backend (es. `/api/radar?tickers=...&window=...`).
2. Backend:

   - scarica/recupera i dati di prezzo (yfinance, ecc.),
   - calcola:
     - variazioni,
     - energie cinetica/potenziale,
     - z-score,
     - stato del “regime di mercato” per ogni asset.
   - restituisce JSON con:
     - valori normalizzati,
     - label di stato (Overheating, Volatility, Equilibrium, Accumulation),
     - eventuali indicatori aggiuntivi.
3. Frontend converte i dati in grafici Plotly (radar, scatter, timeline, ecc.).

### 3.2 Time travel / storico

1. Frontend richiede dati su uno spettro temporale più ampio.
2. Backend calcola traiettorie storiche degli stati energetici.
3. Frontend usa slider/animazione per mostrare l’evoluzione nel tempo.

### 3.3 Fourier / forecast

1. Frontend invia richiesta per forecast (es. `/api/forecast?ticker=...`).
2. Backend applica analisi spettrale ai dati storici.
3. Backend restituisce:
   - serie osservata,
   - ricostruzione spettrale,
   - eventuale proiezione a breve termine.
4. Frontend visualizza la proiezione con distinzioni visive (storico vs forecast).

### 3.4 STABLE Email Alert (flusso giornaliero)

1. APScheduler attiva `scheduled_stable_job()` all'orario configurato (CronTrigger, Europe/Rome).
2. `run_stable_scan()` in `stable_scanner.py`:
   - Carica config da `stable_alert_config.json`.
   - Carica tickers da `tickers_loader.py`.
   - `download_all_prices()`: verifica PRICE_CACHE → TICKER_CACHE → MarketData.fetch() (stessa infrastruttura di main.py).
   - `compute_stable_signals()`: calcola stable_slope per ogni ticker, identifica entry signals negli ultimi 5 giorni.
   - Classifica segnali in: `entries_today` (trigger oggi), `entries_recent` (1-5 giorni fa), `active` (posizioni aperte).
3. `build_stable_email()`: genera HTML con 3 sezioni colorate (verde/giallo/viola).
4. `NotificationManager.send_email()`: invia via Resend API o SMTP fallback.
5. Risultati ritornati anche alla UI se chiamato via `/stable-alert/trigger-with-result`.

### 3.5 STABLE Strategy Lab (test_stable.html)

1. **Analisi singola**: Frontend chiama `/analyze` con parametri STABLE custom, mostra risultato.
2. **Batch analysis**: Frontend chiama `/analyze` per ogni ticker, costruisce tabella ordinabile con statistiche.
3. **Optimizer**: grid search su range di alpha, ogni combinazione testata via `/analyze`, risultati ordinati per performance.
4. **Email Alert config**: Frontend chiama gli endpoint `/stable-alert/*` per gestire configurazione e trigger.

## 4. Dipendenze e stack

- **Backend**:

  - Python
  - FastAPI
  - Uvicorn
  - Pandas / NumPy / SciPy
  - yfinance (o lib simili per dati di mercato)
  - APScheduler (scheduling email giornaliere)
  - Resend (API cloud per invio email) / smtplib (fallback SMTP)
- **Frontend**:

  - HTML5
  - Vanilla JavaScript
  - Plotly.js
- **Deployment**:

  - Railway (Procfile con comando: `web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT`)

## 5. Decisioni architetturali

- Backend “fat”, frontend “thin”:

  - la logica pesante (calcoli, fisica, forecast) sta tutta nel backend Python;
  - il frontend è principalmente una shell grafica.
- Contratti API stabili:

  - gli schemi Pydantic esposti dalle route vanno trattati come contratti da non rompere,
    soprattutto se l’app verrà poi usata in altri contesti (es. integrazione in piattaforme di terzi).
- Notebook = R&D:

  - non vanno mai usati come layer di produzione;
  - eventuali formule/promesse emerse dai notebook devono essere implementate
    in moduli Python testabili nel backend.
