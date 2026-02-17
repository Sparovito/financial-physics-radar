# Financial Physics Radar — Project Description

## Purpose

Financial Physics Radar è uno strumento di analisi quantitativa progettato per analizzare indici di borsa e asset finanziari
con l’obiettivo di stimare:

- la **direzione probabile del mercato**,
- l’**intensità dei movimenti**,
- il **regime di mercato**,
- possibili **scenari evolutivi nel tempo**.

Il progetto non nasce come sistema di trading automatico, ma come **Decision Support System**
basato su modelli fisici e analisi matematica interpretabile.

## Core Idea

Il mercato viene trattato come un **sistema dinamico fisico**:

- accumula energia,
- la rilascia in modo impulsivo,
- cambia regime,
- oscilla su più scale temporali.

L’obiettivo è descrivere e misurare questi comportamenti tramite modelli quantitativi
ispirati alla fisica, evitando approcci black-box.

## Core Models

Il progetto si basa principalmente su **due famiglie di modelli**:

### 1. Analisi di Fourier / Analisi Spettrale

- decomposizione del movimento dei prezzi in componenti cicliche
- identificazione di frequenze dominanti
- analisi delle transizioni di regime
- studio della struttura temporale del mercato

L’analisi di Fourier è considerata **centrale** e deve essere implementata in modo rigoroso,
controllato e coerente nel tempo.

### 2. Energia Cinetica e Potenziale

- modellazione del mercato tramite grandezze energetiche
- energia cinetica → intensità, accelerazione, dinamica
- energia potenziale → tensione, accumulo, instabilità latente
- interpretazione tramite stati energetici del mercato

Questi modelli permettono di stimare non solo *dove* il mercato potrebbe andare,
ma *con quanta forza*.

## Funzionalità Principali

Il sistema è progettato per supportare:

- analisi live degli indici di mercato
- analisi storica (time travel)
- analisi batch di più asset (azioni, ETF, indici)
- visualizzazioni 2D interattive
- confronto cross-asset
- costruzione di strategie basate sugli indicatori fisici
- valutazione operativa giornaliera (“cosa fare oggi”)
- output automatici (es. email, report)

## Architettura

Il progetto è strutturato come segue:

- **Backend**
  - implementa tutta la logica numerica
  - calcolo FFT, modelli energetici, strategie
  - espone API strutturate
- **Frontend**
  - visualizzazione e interazione
  - nessuna logica numerica complessa
- **Notebook**
  - ricerca, esplorazione e validazione dei modelli
  - non fanno parte del runtime di produzione

## Filosofia del Progetto

- interpretabilità prima dell’automazione
- modelli espliciti, non black-box
- separazione netta tra:
  - ricerca
  - calcolo
  - visualizzazione
- focus su insight e supporto decisionale

## Non-Obiettivi (Vincoli Espliciti)

Il progetto **non è**:

- un trading bot automatico
- un sistema di esecuzione ordini
- un servizio di consulenza finanziaria
- un motore di raccomandazione black-box
- un sistema integrato con broker (per ora)

## Stato Attuale

- modelli FFT ed energetici implementati a livello prototipale
- backend e frontend funzionanti
- analisi storica e live già esplorate manualmente
- 4 strategie implementate: LIVE, FROZEN, SUM, STABLE (causale, viola)
- indicatori stabili (causali) operativi: Stable Kinetic Z con hysteresis, Stable Slope
- scanner massivo con colonne STABLE (sostituisce vecchio MA/Min Action)
- **2 sistemi email giornalieri** schedulati:
  - Email scanner originale (Frozen/Sum segnali BUY/SELL + portfolio HOLD/SELL)
  - **Email STABLE** (segnali ENTRY oggi + recenti <5gg + posizioni attive) — `stable_scanner.py`
- **STABLE Strategy Lab** (`test_stable.html/js`): pagina dedicata con 4 tab:
  - Analisi singola, Batch massiva, Optimizer con grid search alpha, Configurazione Email Alert
- Sistema download unificato: `PRICE_CACHE` + `TICKER_CACHE` + `MarketData.fetch()` condiviso tra main.py e stable_scanner.py
- Nessun dato mock/sintetico: `MarketData.fetch()` lancia `ValueError` su dati Yahoo vuoti
- Portfolio tracking con segnali HOLD/SELL basati su strategie attive

## Direzione Futura

- consolidamento matematico dei modelli
- miglioramento della componente spettrale
- formalizzazione delle strategie
- ulteriore automazione degli output operativi (alert real-time, dashboard)
- miglioramento UX e interpretazione visiva
- ottimizzazione parametri STABLE per asset class specifiche

---

Questo file descrive **l’intento del progetto** e costituisce riferimento stabile
per sviluppatori e coding agent.
