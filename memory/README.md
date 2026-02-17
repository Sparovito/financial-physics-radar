
# Financial Physics Radar

Financial Physics Radar è uno strumento di analisi quantitativa che applica modelli ispirati alla fisica
per interpretare il comportamento degli indici di borsa e degli asset finanziari.

L’obiettivo è stimare:

- **direzione del mercato**,
- **intensità dei movimenti**,
- **regime di mercato**,
- **possibili scenari evolutivi**,

attraverso modelli interpretabili e non black-box.

---

## Core Concept

Il mercato viene trattato come un **sistema dinamico fisico**:

- accumula energia,
- la rilascia in modo impulsivo,
- cambia regime,
- oscilla su più scale temporali.

Il progetto nasce per trasformare questa visione in **indicatori quantitativi leggibili**
e in **supporto operativo**.

---

## Modelli Principali

### 1. Analisi di Fourier / Analisi Spettrale

- decomposizione ciclica del movimento dei prezzi
- individuazione di frequenze dominanti
- analisi delle transizioni di regime
- studio della struttura temporale del mercato

La componente Fourier è centrale e viene trattata come modello strutturale,
non come semplice indicatore accessorio.

### 2. Energia Cinetica e Potenziale

- energia cinetica → dinamica, accelerazione, intensità
- energia potenziale → tensione, accumulo, instabilità latente
- interpretazione del mercato tramite stati energetici

Questi modelli permettono di stimare **non solo dove** il mercato può andare,
ma **con quanta forza**.

---

## Funzionalità

- analisi live di indici e asset
- analisi storica (time travel)
- analisi batch multi-asset (scanner massivo)
- visualizzazioni 2D interattive (Plotly)
- confronto cross-asset (radar)
- 4 strategie di backtest: LIVE, FROZEN, SUM, STABLE
- indicatori stabili causali (Stable Kinetic Z, Stable Slope)
- valutazione operativa giornaliera ("cosa fare oggi")
- **2 sistemi email giornalieri schedulati**:
  - Email scanner originale (segnali BUY/SELL da Frozen/Sum + portfolio HOLD/SELL)
  - Email STABLE (segnali ENTRY oggi + recenti <5gg + posizioni attive)
- **STABLE Strategy Lab** (test_stable.html): pagina dedicata con optimizer, batch analysis, email config
- portfolio tracking con segnali HOLD/SELL

---

## Architettura

Il progetto è strutturato in tre livelli:

### Backend

- Python + FastAPI
- fetch dati di mercato
- modelli FFT ed energetici
- calcolo indicatori e strategie
- API strutturate

### Frontend

- HTML + JavaScript + Plotly
- visualizzazione e interazione
- nessuna logica numerica complessa

### Notebook

- ricerca e prototipazione
- validazione delle idee
- **non** parte del runtime di produzione

---

## Filosofia

- interpretabilità prima dell’automazione
- modelli espliciti, non black-box
- separazione chiara tra:
  - ricerca
  - calcolo
  - visualizzazione
- focus su insight e supporto decisionale

---

## Non-Obiettivi

Questo progetto **non è**:

- un trading bot automatico
- un sistema di esecuzione ordini
- un servizio di consulenza finanziaria
- un recommendation engine black-box
- un sistema integrato con broker (per ora)

---

## Stato del Progetto

- prototipo avanzato funzionante
- modelli FFT ed energetici implementati a livello baseline
- backend e frontend operativi
- analisi storica e live già esplorate manualmente
- 4 strategie operative: LIVE, FROZEN, SUM, STABLE (causale, viola)
- indicatori stabili causali: Stable Kinetic Z (EMA + hysteresis), Stable Slope
- scanner massivo con colonne STABLE (ha sostituito MA/Min Action)
- 2 email giornaliere schedulate: scanner originale (16:30) + STABLE alert (configurabile)
- STABLE Strategy Lab con optimizer, batch, email alert config
- sistema download unificato (PRICE_CACHE + TICKER_CACHE + MarketData)
- nessun dato mock: ValueError su dati Yahoo vuoti

---

## File di Riferimento

Per comprendere e lavorare correttamente sul progetto:

- `memory/PROJECT_DESCRIPTION.md` → descrizione concettuale del progetto
- `memory/ARCHITECTURE.md` → struttura del sistema e moduli
- `memory/SYSTEM_OVERVIEW.md` → deep dive tecnico completo
- `memory/CHANGELOG.md` → storico completo di tutti i deploy e modifiche
- `memory/INVARIANTS.md` → regole supreme (leggere PRIMA di ogni modifica)
- `memory/PROJECT_RULES.md` → regole di sviluppo (incluse regole per coding agent)
- `requirements.txt` → dipendenze Python
- `Procfile` → configurazione di deployment

---

## Disclaimer

Questo progetto ha scopo di ricerca, analisi e supporto decisionale.
Non fornisce consulenza finanziaria né raccomandazioni di investimento.
