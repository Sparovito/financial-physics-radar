# Financial Physics Market Radar — PROJECT RULES

Queste regole valgono per chiunque modifichi il codice, inclusi coding agent/LLM
(Gemini, Claude, GPT, Antigravity, ecc.).

## 1. Scope del progetto

- Il progetto è un’app FastAPI + frontend statico Plotly per visualizzare stati “fisici” del mercato.
- L’obiettivo è mantenere:
  - API stabili,
  - codice leggibile e testabile,
  - separazione chiara tra logica numerica e presentazione.

## 2. Regole GENERALI per i coding agent

1. **Non reinventare l’architettura.**
   - Rispetta la struttura descritta in `ARCHITECTURE.md`.
   - Non spostare moduli tra cartelle senza richiesta esplicita.

2. **Non toccare file non forniti nel task.**
   - Se in input hai solo alcuni file, puoi modificare *solo* quelli.
   - Se pensi serva modificare altri file, prima proponi un piano testuale.

3. **Contratti API = sacri.**
   - Non cambiare:
     - path delle endpoint pubbliche,
     - nomi dei campi nei modelli Pydantic esposti,
     - struttura del JSON di risposta.
   - Eccezione: solo se il task specifica esplicitamente una modifica di contratto.

4. **Niente “refactor globali” spontanei.**
   - Vietato:
     - rinominare in massa funzioni/classi/moduli,
     - cambiare lo stile dell’intero progetto in un colpo solo.
   - Ok piccoli refactor locali che migliorano leggibilità o riducono duplicazioni.

5. **Piano → poi codice.**
   - Prima di scrivere patch, l’agente deve:
     - proporre un piano numerato,
     - indicare file coinvolti,
     - descrivere eventuali impatti su API/contratti.
   - Solo dopo il via libera si passa alle modifiche.

6. **Diff granulari, non riscritture monolitiche.**
   - Fornire modifiche sotto forma di patch/diff ove possibile.
   - Evitare di riscrivere completamente file lunghi se servono solo correzioni locali.

## 3. Backend rules

- Linguaggio: Python.
- Framework: FastAPI.

### 3.1 Route e modelli

- Le route pubbliche (es. `/`, `/api/radar`, `/api/forecast`, `/api/assets`, ecc.)
  devono mantenere la loro semantica.
- I modelli Pydantic associati alle risposte (DTO) sono considerati **contratti stabili**.
- Non cambiare:
  - nomi dei campi,
  - tipi dei campi,
  - annidamento delle strutture,
  - significato semantico.

Se serve un nuovo formato di risposta:
- aggiungere **nuove** route o nuovi modelli,
- non rompere quelle esistenti.

### 3.2 Logica numerica

- Moduli come `physics_engine`, `fourier_forecast`, `zscore_utils` ecc. contengono logica numerica.
- Le modifiche devono:
  - mantenere la stessa **interfaccia** (nomi di funzioni, parametri),
  - introdurre eventualmente parametri opzionali con default retro-compatibile.

- Prima di qualsiasi refactor numerico:
  - preservare il significato delle grandezze (es. energia cinetica/potenziale),
  - non cambiare silentemente definizioni matematiche.

## 4. Frontend rules

- Linguaggio: HTML + JS + Plotly.
- Il frontend:
  - chiama il backend via fetch/XHR,
  - non deve implementare logica numerica pesante.

Regole:
- Non hardcodare URL di API diversi da quelli attuali (es. evitare di cambiare `http://127.0.0.1:8000` a caso).
- Mantenere i nomi delle chiavi JSON in linea con i contratti del backend.
- È consentito:
  - migliorare UX/UI,
  - riorganizzare il codice JS per maggiore pulizia,
  - aggiungere nuove visualizzazioni, purché non rompano quelle esistenti.

## 5. Notebook e sperimentazione

- `*.ipynb` sono ambienti di ricerca:
  - non vanno mai usati come “codice di produzione”,
  - l’agente **non deve** spostare logica di produzione dentro notebook.

- Se dai notebook emergono miglioramenti:
  - estrarli in moduli Python nel backend,
  - aggiungere test se possibile.

## 6. Stile e qualità

- Preferire funzioni pure e moduli coesi.
- Evitare side-effect nascosti.
- Nominare le funzioni in modo descrittivo, specialmente nel dominio “physics-finance”.
- I commenti devono spiegare *perché* una scelta è stata fatta, non *cosa* fa una riga ovvia.

## 7. Cosa fare in caso di dubbio

Se un coding agent “non è sicuro”:
1. Deve fermarsi.
2. Deve proporre:
   - alternativa A (minimo impatto),
   - alternativa B (refactor più profondo, ma motivato).
3. Deve esplicitare pro e contro di ciascuna.

Se non è chiaro l’impatto sull’architettura:
- l’agente deve chiedere conferma prima di modificare più di un file core.