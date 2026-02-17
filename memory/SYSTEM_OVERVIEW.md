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
    -   Gestisce il download, la pulizia dei dati e la robustezza (fallback a dati mock se offline).
-   **`FourierEngine`**:
    -   Implementa l'Analisi Spettrale.
    -   Esegue FFT (Fast Fourier Transform) sugli ultimi 252 giorni (1 anno).
    -   Genera "scenari futuri" ricostruendo il segnale dalle armoniche dominanti (`top_k`).
-   **`ActionPath`**:
    -   Calcola le metriche energetiche.
    -   **Energia Cinetica ($K$):** Misura la violenza del movimento (Proxy: Volatilità/Velocity).
    -   **Energia Potenziale ($U$):** Misura la tensione accumulata (Proxy: Deviazione dalla media/trend).
    -   Implementa il concetto di "Minima Azione" per tracciare il percorso ideale del prezzo.
-   **`MarketScanner`**:
    -   Parallelizza l'analisi su centinaia di ticker.
    -   Calcola Z-Scores (deviazioni standard) per normalizzare i dati e renderli comparabili tra asset diversi.

#### `analysis.py` - L'Orchestratore
Funge da facciata ("Facade") per `logic.py`.
-   Espone la funzione `run_analysis(...)`.
-   Coordina: Fetch Dati -> Calcolo Fourier -> Calcolo Energie -> Packaging della risposta JSON.

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
-   **`compute_stable_signals()`**: finestra 6 mesi auto-calcolata, download e computazione paralleli (ThreadPoolExecutor 8 workers).
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
-   **Tab Optimizer**: grid search su range di alpha per trovare configurazione ottimale con metriche (Win Rate, Total P/L, Sharpe).
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
Gestisce **due posizioni in parallelo** con backtest custom (non usa `backtest_strategy()`):

**LONG leg:**
-   Entry: stable_slope > 0.0 (slope positiva → trend rialzista)
-   Exit: stable_slope < -0.3 (trend cala forte)
-   Hysteresis: tra -0.3 e 0, LONG resta aperto

**SHORT leg (in parallelo):**
-   Entry: stable_slope < 0.0 (slope negativa → trend ribassista)
-   Exit: stable_slope > 0.2 (trend risale)
-   Hysteresis: tra 0 e 0.2, SHORT resta aperto

**P/L curve**: combinato LONG+SHORT (entrambe le posizioni contribuiscono).
**Output**: formato identico a `backtest_strategy()` (equity_curve, trades, trade_pnl_curve, stats).
-   **Scanner**: lo scanner chiama `/analyze` per ogni ticker, quindi riceve `stable_strategy` con la stessa logica.

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
| **logic.py** | `backend/logic.py` | Modelli Fisici | *Non modificare la matematica senza approvazione*. `MarketData.fetch()` raises ValueError su dati vuoti (no mock fallback). |
| **analysis.py** | `backend/analysis.py` | Workflow Analisi | Colla tra dati e modelli |
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

### Scheduler Re-init
Quando l'utente salva una nuova configurazione (orario diverso), `_init_stable_scheduler()` rimuove il job esistente e ne crea uno nuovo con il nuovo orario.

---
*Questo documento è generato automaticamente dall'analisi del codice e della documentazione normativa.*
