# Financial Physics Radar — INVARIANTS (Non-Negotiables)

Questo documento definisce le invarianti del progetto.
È VINCOLANTE per sviluppatori e coding agent (Claude, Gemini, GPT, Antigravity, ecc.).

Regola madre:

> Nulla che esiste già (funzioni, endpoint, contratti, semantica, output) può essere modificato,
> rinominato, spostato o riscritto, **a meno che non sia esplicitamente richiesto** nel task corrente.

Se un coding agent non è sicuro dell’impatto, deve fermarsi e chiedere conferma.

---

## 1) Invarianti di Scopo

1. Il progetto è un **Decision Support System** per analisi di mercato.
2. Il progetto **NON** è:
   - un trading bot automatico,
   - un sistema di esecuzione ordini,
   - un servizio di consulenza finanziaria,
   - un recommendation engine black-box,
   - un’integrazione con broker (a meno di decisione esplicita futura).
3. “Previsione” significa **stima di scenario/direzione/intensità**, non raccomandazione operativa automatica.

---

## 2) Invarianti di Architettura

1. **Backend fat / Frontend thin**:
   - tutta la logica numerica (FFT, energie, strategie) vive nel backend,
   - il frontend fa visualizzazione e interazione (Plotly/JS), non calcoli complessi.
2. I notebook (`*.ipynb`) sono **solo ricerca**:
   - non diventano runtime di produzione,
   - non sono la fonte di verità dei modelli di produzione.
3. È vietato cambiare stack o introdurre framework alternativi senza richiesta esplicita.

---

## 3) Invarianti dei Modelli (Semantica)

Queste definizioni sono concettualmente stabili:

1. **Fourier / analisi spettrale** è uno dei due modelli core.
   - Può essere migliorata l’implementazione (bugfix/robustezza),
   - ma NON va sostituita con un approccio diverso senza richiesta esplicita.
2. **Energia cinetica e potenziale** sono l’altro modello core.
   - Le grandezze “energia cinetica”, “energia potenziale”, “regime” e “intensità”
     non devono cambiare significato senza una richiesta esplicita e documentata.
3. Qualsiasi modifica che alteri il significato dei segnali o degli indicatori è considerata
   **breaking change concettuale** e richiede approvazione manuale.

---

## 4) Invarianti di Interfaccia (API & Output)

1. Le API pubbliche sono **contratti stabili**.
2. È vietato (senza richiesta esplicita):
   - cambiare path degli endpoint,
   - cambiare query params richiesti/opzionali in modo non retrocompatibile,
   - cambiare struttura delle risposte JSON,
   - rinominare chiavi JSON,
   - cambiare unità/scala/interpretazione di campi già esposti.
3. Se serve un nuovo formato:
   - aggiungere nuovi endpoint o nuove versioni (`/v2/...`) senza rompere l’esistente,
   - oppure aggiungere campi **nuovi** in modo backward-compatible (mai rimuovere/cambiare quelli esistenti).

---

## 5) Invarianti di Funzioni (Code Freeze Policy)

### 5.1 Regola generale (blocco totale)

- Qualsiasi funzione, classe, modulo, endpoint o file esistente è considerato **frozen**:
  - non va rinominato,
  - non va spostato,
  - non va riscritto,
  - non va “ripulito”,
  - non va “ottimizzato”,
    a meno che il task corrente lo richieda esplicitamente.

### 5.2 Eccezioni consentite (solo se NON cambiano comportamento)

Sono ammesse modifiche **non funzionali**, solo se non cambiano l’output:

- commenti e docstring (senza cambiare logica),
- formatting/linting locale non invasivo,
- log/telemetria senza alterare valori o flussi,
- gestione errori che non cambia i risultati in condizioni normali.

Se c’è anche solo un dubbio che cambi l’output, il coding agent deve:

1) fermarsi,
2) descrivere l’impatto,
3) chiedere conferma.

---

## 6) Invarianti di Stabilità Operativa

1. Non introdurre dipendenze nuove senza motivo e senza richiesta esplicita.
2. Non cambiare la logica di fetch dati o la sorgente dati senza richiesta esplicita.
3. Non cambiare default di parametri che influenzano risultati senza richiesta esplicita.
4. Non cambiare comportamento “live vs historical” senza richiesta esplicita.

---

## 7) Protocollo Obbligatorio per Modifiche (LLM Workflow)

Per qualsiasi task, un coding agent deve:

1. Proporre un piano (max 5 punti).
2. Elencare esattamente i file che intende toccare.
3. Dichiarare esplicitamente se l’intervento impatta:
   - contratti API,
   - semantica indicatori,
   - output numerici.
4. Fornire patch/diff limitate allo scope.
5. Se il task richiede modifiche potenzialmente “breaking”:
   - fermarsi e chiedere approvazione prima di implementare.

---

## 8) Come richiedere eccezioni (testo minimo)

Per sbloccare una modifica “frozen”, il task deve includere esplicitamente una frase tipo:

> "È richiesto modificare/riscrivere/rinominare la funzione X nel file Y per ottenere Z.
> Accetto breaking changes su [API/semantica/output] se necessari."

Senza una frase simile, la modifica è considerata non autorizzata.

---

## 9) Note finali

Questo file ha priorità su:

- suggerimenti dell’LLM,
- refactor “migliorativi”,
- ottimizzazioni “pulizia codice”.

L’obiettivo è proteggere il progetto da regressioni e perdita di coerenza.
