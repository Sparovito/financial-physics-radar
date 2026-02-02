# Financial Physics Radar 📡

## 🔭 Cos'è il progetto
**Financial Physics Radar** è un sistema di supporto decisionale (DSS) per l'analisi quantitativa dei mercati finanziari.
A differenza dei comuni strumenti di analisi tecnica, questo progetto applica **modelli fisici** (Energia Cinetica, Potenziale, Minima Azione) e **analisi spettrale** (Fourier) per stimare:
- La direzione probabile del mercato.
- L'intensità dei movimenti.
- Il regime di mercato corrente.

L'obiettivo fondamentale è fornire metriche oggettive e interpretabili, evitando approcci "black-box".

## 🎯 A chi è rivolto
Questo strumento è pensato per:
- **Analisti Quantitativi e Trader** che cercano un approccio scientifico e non convenzionale ai mercati.
- **Ricercatori** interessati all'applicazione di modelli fisici e numerici alle serie storiche finanziarie.
- Chiunque voglia superare l'analisi tecnica tradizionale con strumenti basati su segnali energetici e ciclici.

## 🏗️ Architettura ad Alto Livello
Il sistema segue un'architettura **Fat Backend / Thin Frontend**:

- **Backend (Python + FastAPI)**: Il "cervello" del sistema. Gestisce il download dei dati (Yahoo Finance), calcola le trasformate di Fourier (FFT), le energie (Cinetica/Potenziale) e simula le strategie.
- **Frontend (HTML/JS + Plotly)**: Il "visore". Si occupa esclusivamente di visualizzare i grafici interattivi e gestire la "Time Machine" per l'analisi storica.
- **Notebooks**: Laboratorio di ricerca per prototipare nuovi modelli matematici prima dell'integrazione.

## 📚 Documentazione
Per approfondire i dettagli del progetto, consulta la documentazione dedicata nella cartella `memory/`:

- **[Descrizione del Progetto](memory/PROJECT_DESCRIPTION.md)**: Visione concettuale e filosofia.
- **[Panoramica del Sistema](memory/SYSTEM_OVERVIEW.md)**: Dettagli tecnici approfonditi su moduli, calcoli e flussi dati.
- **[Architettura](memory/ARCHITECTURE.md)**: Struttura dettagliata dei componenti software.
- **[Regole del Progetto](memory/PROJECT_RULES.md)**: Linee guida per lo sviluppo e il mantenimento del codice.
