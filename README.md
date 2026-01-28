
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
- analisi batch multi-asset
- visualizzazioni 2D interattive
- confronto cross-asset
- supporto alla costruzione di strategie
- valutazione operativa giornaliera (“cosa fare oggi”)
- output automatici (email / report)

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
- strategie in fase di definizione
- automazione output in progettazione

---

## File di Riferimento

Per comprendere e lavorare correttamente sul progetto:

- `PROJECT_DESCRIPTION.md` → descrizione concettuale del progetto
- `ARCHITECTURE.md` → struttura del sistema
- `PROJECT_RULES.md` → regole di sviluppo (incluse regole per coding agent)
- `requirements.txt` → dipendenze Python
- `Procfile` → configurazione di deployment

---

## Disclaimer

Questo progetto ha scopo di ricerca, analisi e supporto decisionale.
Non fornisce consulenza finanziaria né raccomandazioni di investimento.
