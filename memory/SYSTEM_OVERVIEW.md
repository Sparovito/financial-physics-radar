# Financial Physics Market Radar — System Overview

Questo documento serve da **base di conoscenza completa** del progetto. Analizza l'architettura, la logica e il codice sorgente per fornire una visione unificata del sistema.  
*Ultimo aggiornamento: 17 Febbraio 2026*

---

## 1. Identità del Progetto

**Nome:** Financial Physics Radar  
**Scopo:** Decision Support System (DSS) per l'analisi dei mercati finanziari.  
**Filosofia:** Applicare modelli fisici (Energia, Fourier, Minima Azione) per quantificare lo stato del mercato, evitando approcci black-box.

### Core Concepts
1.  **Mercato come Sistema Fisico:** Accumula energia (Potenziale) e la rilascia (Cinetica).
2.  **Analisi Spettrale (Fourier):** Scompone i movimenti di prezzo in cicli per identificare frequenze dominanti e proiettare scenari.
3.  **Time Travel:** Capacità di simulare l'analisi in qualsiasi punto del passato per validare le strategie senza look-ahead bias (modalità "Frozen").

---

## 2. Architettura del Sistema

Il sistema segue un pattern strict **Fat Backend / Thin Frontend**.

### Backend (Python/FastAPI)
-   **Ruolo:** "Il Cervello". Gestisce dati, calcoli fisici, simulazioni e strategie.
-   **Responsabilità:**
    -   Download dati (Yahoo Finance).
    -   Motore Fisico (Cinetica/Potenziale, Z-Scores).
    -   Motore Fourier (FFT, Scenari).
    -   Simulazione Storica (Backtest, Frozen States).

### Frontend (HTML/JS/Plotly)
-   **Ruolo:** "Il Visore". Visualizza i dati calcolati dal backend.
-   **Responsabilità:**
    -   Rendering grafici (Plotly.js).
    -   Gestione interazione utente (Time slider, Toggles).
    -   Nessuna logica di calcolo complessa.

---

## 3. Analisi del Codice (Deep Dive)

### 3.1 Backend: I Motori (`backend/`)

#### `logic.py` - Il Cuore Matematico
Questo file contiene le classi fondamentali che implementano i modelli fisici.
-   **`MarketData`**:
    -   Wrapper per `yfinance`.
    -   Gestisce il download e la pulizia dei dati; lancia `ValueError` su dati vuoti.
-   **`FourierEngine`**:
    -   Implementa l'Analisi Spettrale.
    -   Esegue FFT (Fast Fourier Transform) su una finestra configurabile (default 504 giorni).
    -   Genera "scenari futuri" ricostruendo il segnale dalle armoniche dominanti (`top_k`).
-   **`ActionPath`**:
    -   Calcola le metriche energetiche.
    -   **Energia Cinetica ($K$):** Misura la violenza del movimento (Proxy: Volatilità/Velocity).
    -   **Energia Potenziale ($U$):** Misura la tensione accumulata (Proxy: Deviazione dalla media/trend).
    -   Implementa il concetto di "Minima Azione" per tracciare il percorso ideale del prezzo.
    -   **NOTA MATEMATICA (2026-07-05):** il percorso di minima azione è lo
        smoother MAP di un modello state-space local-level gaussiano
        (q=1/α, r=1/β, init diffusa). NON è causale: x*(t) dipende anche dal futuro.
-   **`kalman_frozen_series(px, alpha, beta)`** *(2026-07-05)*:
    -   Serie "frozen" point-in-time in **O(n)** via filtro di Kalman + fixed-lag smoother.
    -   Valori NUMERICAMENTE IDENTICI al vecchio ricalcolo `ActionPath(px[:t+1])`
        per ogni t (O(n²)) — parità in `tests/test_kalman_frozen.py`, speedup ~73x.
    -   Fondamento: l'ultimo punto dello smoother su [0..t] = filtro di Kalman al tempo t.
-   **`causal_lowpass(values)`** *(2026-07-05)*:
    -   Butterworth passa-basso CAUSALE (lfilter + lfilter_zi). Sostituisce `filtfilt`
        (zero-phase, bidirezionale = lookahead) nel segnale Frozen SUM.
-   **`compute_stable_kinetic_z(px, alpha)`** *(2026-07-05)*:
    -   Calcolo S.KinZ estratto e testato (il blocco inline in main.py referenziava
        una variabile inesistente: il pannello riceveva sempre dati vuoti).
-   **`backtest_strategy(..., execution_lag=1)`**:
    -   Backtest LIVE/FROZEN/SUM/MA. Da 2026-07-05 il segnale della barra j
        viene eseguito al close della barra j+1 (default; `execution_lag=0` = legacy).
-   **`MarketScanner`**:
    -   Parallelizza l'analisi su centinaia di ticker.
    -   Calcola Z-Scores rolling; serie frozen via `kalman_frozen_series` (O(n)).

#### `stable_strategy.py` - Motore STABLE Unificato *(2026-07-05)*
L'UNICA implementazione della strategia STABLE (vedi sezione dedicata sotto).
Replica JS speculare in `frontend/stable_engine.js`; parità verificata da
`tests/test_js_py_parity.py`. (Il vecchio `analysis.py` era codice morto e
rotto — non importato da nulla — ed è stato rimosso; la versione viva di
run_analysis vive in `main.py::analyze_stock`.)

#### `tests/` - Suite di Test *(2026-07-05)*
Script standalone (`venv/bin/python tests/test_*.py`), nessuna dipendenza nuova:
parità Kalman, causalità S.KinZ e SUM, motore STABLE (8 scenari), parità JS↔PY
(richiede node), scanner segnali, verifica integrità con cache sintetica.

#### `main.py` - L'Interfaccia API
Configura il server FastAPI ed espone gli endpoint.
-   **`/api/radar`**: Endpoint principale. Innesca `run_analysis`.
-   **`/api/scanner`**: Esegue scansioni massive di mercato.
-   **`/api/verify_integrity`**: Endpoint critico per verificare che le simulazioni storiche non barino (no look-ahead bias).
-   **`/stable-alert/*`**: 5 endpoint per gestione email alert STABLE (config, trigger, test, trigger-with-result).
-   **Scheduler**: APScheduler con 2 job CronTrigger (email scanner originale + STABLE alert), timezone Europe/Rome.
-   **Cache condivise**: `PRICE_CACHE` (thread-safe), `TICKER_CACHE` — usate da `main.py` e `stable_scanner.py`.

#### `stable_scanner.py` - Email Alert STABLE
Modulo dedicato per le email giornaliere con segnali della strategia STABLE.
-   **`download_all_prices()`**: riutilizza `PRICE_CACHE`, `TICKER_CACHE` e `MarketData` da `main.py` (stessa infrastruttura).
-   **`analyze_ticker_signals()`** *(2026-07-05)*: segnali derivati dal MOTORE
    UNIFICATO (`stable_strategy.backtest_stable`) — stessa semantica di Lab e
    Strategia 5 (level-based, SHORT speculare, esecuzione t+1). I segnali con
    `pending_execution=True` vanno eseguiti alla prossima barra.
-   **`drop_partial_last_bar()`** *(2026-07-05)*: scarta la barra di OGGI se
    calcolata prima delle 22:05 Europe/Rome (candela Yahoo incompleta →
    repainting). Default trigger email: **22:30 Rome** (dopo chiusura USA).
-   **`compute_stable_signals()`**: finestra auto (6 mesi STABLE, 24 mesi
    ARANCIONE/COMBO per warmup Kalman+z), download e computazione paralleli.
-   **Strategia configurabile** *(2026-07-06)*: config `strategy`
    (STABLE/ARANCIONE/COMBO) + `entry_z`/`horizon`; entries con `kind`
    PANIC/TREND e z_pot come "Segnale"; posizioni attive con `days_left`.
-   **Forward test** *(2026-07-06)*: `forward_test.py` — journal persistente
    dei segnali reali (paper trading a quota fissa: pending → open alla barra
    successiva → closed a orizzonte, P&L con costi identico al motore).
    Aggiornato a ogni scan (`price_sink`), sezione 🧪 nell'email, endpoint
    `GET /forward-test/status` e `POST /forward-test/reset` (archivia).
    Il journal (`forward_test_journal.json`) è dato operativo, in .gitignore.
-   **`build_stable_email()`**: HTML con 3 sezioni: ENTRY OGGI (verde), INGRESSI RECENTI <5gg (giallo con badge giorni), POSIZIONI ATTIVE (viola).
-   **`load_config()` / `save_config()`**: persistenza in `stable_alert_config.json`.
-   **Principio critico**: NO `yf.download` batch separato — usa esclusivamente il sistema di download del main app per evitare rate-limiting Yahoo.

#### `notifications.py` - Sistema Email
-   **`NotificationManager`**: dual send Resend API (cloud, prioritario) / SMTP fallback (locale).
-   Credenziali via env vars: `RESEND_API_KEY`, `EMAIL_SENDER`, `EMAIL_RECIPIENT`.
-   Mock print se credenziali mancanti (per sviluppo locale).

#### `scanner.py` - Email Scanner Originale
-   **`run_market_scan()`**: scansione email per segnali BUY/SELL dalle strategie Frozen e Sum.
-   Email HTML con 4 sezioni: BUY OGGI, BUY RECENTI, SELL OGGI, PORTAFOGLIO (HOLD/SELL).
-   Invalidazione cache per ticker del portafoglio prima della scansione.

#### `tickers_loader.py` - Loader Tickers
-   **`load_tickers()`**: legge `tickers.js` dal frontend, converte sintassi JS→JSON, ritorna `{symbol: category}`.

### 3.2 Frontend: La Visualizzazione (`frontend/`)

#### `app.js` - Il Controller UI
Il file JavaScript più critico (oltre 3000 righe).
-   **Gestione Stato:** Mantiene in memoria i dati scaricati (`window.LAST_ANALYSIS_DATA`) per aggiornamenti rapidi senza rifare chiamate API.
-   **Plotly Integration:** Costruisce grafici complessi con multiple tracce:
    -   Price Chart (Candle/Line).
    -   Energy Chart (Subplot).
    -   Fourier Projection (Linee tratteggiate).
    -   Portfolio Markers (Linee/Punti verdi e rossi per i trade).
    -   S.KinZ Panel: regime colorato (verde bull / rosso bear), soglie ±0.5, overlay Kinetic Z viola.
    -   P/L Panel: tracce LIVE (verde), FROZEN (arancione), SUM (rosso), STABLE (viola `#aa44ff`).
-   **Time Travel Logic:** Gestisce lo slider temporale che "taglia" i dati inviati a Plotly per simulare il passato.

#### `test_stable.html` & `test_stable.js` - STABLE Strategy Lab
Pagina dedicata alla strategia STABLE, separata dalla dashboard principale.
-   **Tab Analisi**: analisi singolo ticker con parametri STABLE configurabili (mode, entry_threshold, exit_threshold, alpha).
-   **Tab Batch**: analisi massiva di tutti i ticker (o preset) con tabella ordinabile, statistiche aggregate.
-   **Tab Optimizer**: grid search su range di alpha con **validazione out-of-sample**
    *(2026-07-05)*: i parametri si scelgono sul segmento train (default 70% del periodo),
    la colonna OOS mostra il ritorno sul periodo mai visto — il numero che conta.
-   **Backtest nel browser**: `stable_engine.js` (replica speculare del motore Python),
    esecuzione t+1, costi per lato configurabili, colonne B&H / vs B&H / Sharpe / Expo.
-   **Tab 📩 Email Alert**: configurazione completa email giornaliere:
    -   Toggle ON/OFF con switch visuale.
    -   Orario trigger configurabile (ora/minuto).
    -   Parametri strategia (mode LONG_ONLY/SHORT_ONLY/DUAL, entry/exit threshold, alpha).
    -   Preset ticker (All, US Highlights, Tech, Banks, ecc.) o tickers custom.
    -   Pulsanti: Salva Config, Invia Ora (con preview), Ricarica Config.
    -   Info scheduler (stato e prossima esecuzione).
    -   Preview risultati in tempo reale con 3 sezioni colorate.

#### `index.html` & `style.css`
-   Layout responsive (ottimizzato anche per mobile).
-   Struttura a "dashboard" con sidebar di controllo e area grafici principale.

---

## 4. Flussi di Lavoro Critici

### Analisi "Time Travel" (Frozen State)
1.  L'utente sposta lo slider temporale o clicca su una data passata.
2.  Il Frontend visualizza i dati *come se* fosse quel giorno (nasconde il futuro reale).
3.  **Backend Integrity:** Il backend calcola gli indicatori "Frozen" (congelati) usando SOLO i dati disponibili fino a quella data, garantendo che l'analisi storica sia onesta.

### Strategie di Trading (Simulate)
Il sistema implementa diverse logiche di trading simulate nel backend (`backtest_strategy` in `logic.py`):
1.  **LIVE Strategy:** Usa i segnali attuali.
2.  **FROZEN Strategy:** Usa i segnali "congelati" storici (più realistica).
3.  **SUM Strategy (Minima Azione ibrida):** Combina Z-Score e trend direzionale.
4.  **STABLE Strategy (🟣 viola):** Dual LONG+SHORT in parallelo sulla **Stable Slope** (linea verde F.Slope). LONG: entry slope>0, exit slope<-0.3. SHORT: entry slope<0, exit slope>0.2. Backtest custom (non usa `backtest_strategy`). Implementata come STRATEGIA 5 nel backend.

### STABLE Strategy — Dettaglio Implementazione (STRATEGIA 5)
La strategia viola usa la **Stable Slope** (`stable_slope_line` = EMA(14) di dF, linea verde nel pannello F.Slope).

**[UNIFICATA 2026-07-05]** Esiste UNA SOLA implementazione di riferimento:
`backend/stable_strategy.py::backtest_stable()`, usata da:
-   Strategia 5 in `main.py` (LONG-only, soglie 0/0)
-   STABLE Lab (`frontend/stable_engine.js` = replica speculare JS, parità
    garantita da `backend/tests/test_js_py_parity.py`)
-   Email scanner (`stable_scanner.py::analyze_ticker_signals`)

**Semantica unificata:**
-   Segnale valutato sul close della barra j, **esecuzione al close della barra j+1**
    (`execution_lag=1`; 0 = vecchio same-bar, solo per confronto)
-   LONG: entry slope > entry_th, exit slope < exit_th
-   SHORT: soglie **speculari** — entry slope < -entry_th, exit slope > -exit_th
-   BOTH: due leg paralleli indipendenti, capitale condiviso
-   Costi di transazione parametrici (`cost_pct` % per lato)
-   Win rate / avg trade / profit factor **solo sui trade chiusi**
-   Stats estese: `max_drawdown`, `profit_factor`, `exposure_pct`, `sharpe`,
    `buy_hold_return` (benchmark nello stesso periodo)
-   `signal_events`: eventi ENTRY/EXIT, inclusi PENDENTI (segnale sull'ultima
    barra, esecuzione alla prossima)

**Strategie derivate (2026-07-05, stesse garanzie del motore):**
-   **ARANCIONE — Scarico del Potenziale** (`backtest_potential_discharge`):
    contrarian a eventi. Onset = z-score rolling del potenziale causale
    attraversa `entry_z` dal basso E prezzo < fondamentale (panico);
    posizione LONG per `horizon` barre, estesa su re-spike. Evidenza: unico
    alpha OOS positivo del sistema, robusto su tutta la griglia
    (entry_z 1.5-2.5 × hold 10-42). Esposizione tipica 2-8%: è un satellite.
-   **COMBO** (`backtest_combo`): leg trend STABLE (isteresi entry/exit) in
    OR con il satellite arancione. OOS: Sharpe 0.33→0.44 vs solo trend,
    drawdown invariato. LONG-only (gli spike rialzisti non hanno edge).
-   Mirror JS di entrambe in `frontend/stable_engine.js` (parità testata).
    Lab: selettore strategia + parametri Entry Z / Hold + End Date
    (validazione train/OOS manuale). `/analyze-batch-stable` fornisce anche
    `pot` (potenziale causale Kalman, None-padded) e `fundamental` (EMA20).

### Indicatori Stabili (Causal Indicators) — Pannello S.KinZ
Usati per la visualizzazione nel pannello S.KinZ (NON più per la strategia STABLE). I valori passati **non cambiano mai** aggiungendo nuovi dati.

-   **Stable Kinetic Z:**
    -   Base: EMA(20) forward-only su dF (derivata prezzi), poi `0.5 * alpha * dF_smooth²`.
    -   Z-Score rolling 252 giorni.
    -   **Hysteresis ±0.5:** regime bullish quando Z > +0.5, bearish quando Z < -0.5.
    -   **NON usa `filtfilt`** (non-causale). Usa solo EMA forward-only.
    -   Parametro: `req.alpha` (non `alpha` bare).

-   **Stable Slope:**
    -   Slope stabilizzata, calcolata con metodo causale (EMA(14) su dF).

---

## 5. Mappa dei File Chiave (Recap)

| File | Percorso | Ruolo | Note |
| :--- | :--- | :--- | :--- |
| **logic.py** | `backend/logic.py` | Modelli Fisici | *Non modificare la matematica senza approvazione*. `MarketData.fetch()` raises ValueError su dati vuoti (no mock fallback). Include `kalman_frozen_series`, `causal_lowpass`, `compute_stable_kinetic_z`. |
| **stable_strategy.py** | `backend/stable_strategy.py` | Motore STABLE unificato | Fonte di verità della strategia; replica JS in `frontend/stable_engine.js` (parità testata) |
| **tests/** | `backend/tests/` | Suite di test | Parità Kalman/JS, causalità, motore STABLE, scanner |
| **main.py** | `backend/main.py` | API Server + Scheduler | Definisce contratti JSON, scheduler APScheduler (2 job: email originale + STABLE alert), cache condivise (PRICE_CACHE, TICKER_CACHE) |
| **stable_scanner.py** | `backend/stable_scanner.py` | Email Alert STABLE | Scanner segnali STABLE, download via main.py infra, email HTML 3 sezioni |
| **scanner.py** | `backend/scanner.py` | Email Scanner Originale | Segnali BUY/SELL da Frozen/Sum, email HTML 4 sezioni, portfolio HOLD/SELL |
| **notifications.py** | `backend/notifications.py` | Sistema Email | Resend API + SMTP fallback |
| **tickers_loader.py** | `backend/tickers_loader.py` | Loader Tickers | Legge tickers.js, converte JS→JSON |
| **app.js** | `frontend/app.js` | UI Logic (Dashboard) | Gestisce grafici e interattività, radar, scanner |
| **test_stable.html** | `frontend/test_stable.html` | STABLE Strategy Lab (HTML) | Pagina dedicata con 4 tab: Analisi, Batch, Optimizer, Email Alert |
| **test_stable.js** | `frontend/test_stable.js` | STABLE Strategy Lab (JS) | Logica UI per analisi, batch, optimizer, config email alert |
| **INVARIANTS.md** | `memory/` | Regole Supreme | Leggere PRIMA di ogni modifica |

---

## 6. Decisioni Tecniche Chiave (Lessons Learned)

### Download Dati — Infrastruttura Condivisa (CRITICO)
Il modulo `stable_scanner.py` DEVE riutilizzare la stessa infrastruttura di download di `main.py`:
-   `PRICE_CACHE` + `TICKER_CACHE` + `MarketData.fetch()`.
-   **MAI** usare `yf.download` batch separato — causa rate-limiting Yahoo (633+ errori su 700 ticker).
-   La condivisione della cache evita download doppi e sfrutta dati già scaricati dall'analisi principale.

### Nessun Mock/Fake Data
`MarketData.fetch()` in `logic.py` **lancia `ValueError`** quando Yahoo restituisce dati vuoti. Non c'è fallback a dati sintetici. Il scanner cattura l'errore e aggiunge il ticker alla lista "failed".

### Finestra Dati Email: 6 Mesi
Per le email STABLE, la finestra dati è auto-calcolata a 6 mesi (`today - 180 giorni`). Sufficiente per convergenza EMA, molto più veloce di 3 anni.

### Causal Stable Slope
Formula: `EMA(prices, span=alpha/10)` → `diff()` → `EMA(14)`. Puramente backward-looking, dipendente da alpha. NON usa `filtfilt` (non-causale).

### Causalità end-to-end (2026-07-05)
-   Il segnale Frozen SUM usa `causal_lowpass` (lfilter) al posto di `filtfilt`:
    NESSUN filtro zero-phase è ammesso su segnali usati nei backtest.
-   `/verify-integrity` (bug chiave cache corretto: legge `TICKER_CACHE[ticker]["frozen"]`)
    certifica 0 trade corrotti per FROZEN e SUM su dati reali.
-   Tutti i backtest usano esecuzione t+1 di default (`execution_lag=1`).
-   Le email STABLE calcolano i segnali SOLO su barre daily COMPLETE
    (`drop_partial_last_bar`, trigger default 22:30 Rome).

### Fondamento state-space del modello (2026-07-05)
Il percorso di Minima Azione = smoother di Kalman di un modello local-level
(q=1/α, r=1/β). La versione point-in-time ("frozen") = filtro di Kalman causale,
calcolata in O(n) da `kalman_frozen_series` con valori identici al vecchio
ricalcolo O(n²). Il rapporto segnale/rumore λ=β/α è l'unico parametro reale;
per α=200, β=1 il guadagno steady-state equivale a una EMA di ~28 giorni
(la Stable Slope causale è l'approssimazione steady-state del filtro esatto).

### Scheduler Re-init
Quando l'utente salva una nuova configurazione (orario diverso), `_init_stable_scheduler()` rimuove il job esistente e ne crea uno nuovo con il nuovo orario.

---
*Questo documento è generato automaticamente dall'analisi del codice e della documentazione normativa.*
