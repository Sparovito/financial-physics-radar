# Forward Test — Protocollo

*Regole fissate l'11 novembre 2026, a journal vuoto. Sostituisce la prima
versione del giorno prima, che confrontava i risultati con lo zero.*

## Cosa sappiamo dal backtest (e cosa no)

Rendimento a 21 barre, costi inclusi, 121 titoli, 2021 → 11/2026
(`backend/research/scanner_persistence.py`):

| Cosa si compra | Media |
|---|---|
| Un titolo qualsiasi in un giorno qualsiasi | +1.2% |
| Un titolo qualsiasi in un giorno di segnale | +2.7% |
| Il titolo del segnale | +3.4% |

- Il vantaggio vero non è +3.4% ma **+2.2 punti sulla base**, con una
  significatività a grappoli settimanali di 1.7: indicativa, non provata.
- Viene soprattutto dal **quando** (+1.5: dopo giornate di panico il mercato
  tende a rimbalzare) e poco dal **quale titolo** (+0.7, non distinguibile dal caso).
- Lo stesso vale per l'indice: SPY comprato dopo giorni con molti segnali ha
  reso +3.9% in 21 barre contro +1.1% di un giorno qualsiasi (26 casi).
- Confrontare con lo zero è fuorviante: in un mercato che sale quasi ogni
  acquisto guadagna.

## Cosa registra il journal

Per ogni segnale reale: ingresso al close della prima barra completa
successiva, uscita dopo 21 barre, costi 0.05% per lato, quota fissa. Con la
stessa identica regola registra tre gruppi di confronto, estratti in modo
deterministico (seme = data):

| Gruppo | Cos'è | Cosa misura |
|---|---|---|
| `control` | un titolo a caso lo stesso giorno di ogni segnale | quanto conta *quale* titolo |
| `baseline` | un titolo a caso a ogni scan | quanto conta *quando* si compra |
| `index` | SPY, nei giorni in cui dà segnale almeno il 2% dei titoli | "e comprando solo l'indice?" |

Per ogni trade salva anche il rendimento di SPY sulle stesse date.

Parametri congelati alla creazione del journal: `entry_z=2.0`, `horizon=21`,
potenziale con `alpha=200`, `beta=1`. Ogni cambio successivo è registrato
come violazione. Per cambiarli: `POST /forward-test/reset` e si riparte.

## Il semaforo

Si valuta solo con **almeno 30 trade chiusi in almeno 12 settimane distinte**.

| Condizione | Esito |
|---|---|
| media per trade ≤ 0% | **STOP** |
| media ≥ +1.0% **e** segnali sopra la base giornaliera (se la base ha almeno 10 trade chiusi) | **COERENTE** col backtest |
| altrimenti | **ESTENDI** fino a 60 trade; se resta lì, **NON CONFERMATO** |

## Cosa il semaforo NON è

Non è una prova. Ogni settimana con segnali vale come una sola osservazione
(i trade dello stesso panico si muovono insieme); con un vantaggio atteso di
circa +2 punti servirebbero diversi anni di dati dal vivo per confermarlo
statisticamente. Il forward test serve a:

1. accorgersi presto se dal vivo i risultati sono *incoerenti* col backtest
   (media negativa, segnali sotto la base);
2. controllare che la catena funzioni (segnali su barre complete, ingressi
   t+1, uscite puntuali).

La decisione di usare capitale vero resta un giudizio in condizioni di
incertezza: evidenza indicativa, meccanismo plausibile (rimbalzo dopo il
panico), rischio da contenere con il sizing (quota piccola, massimo 10
posizioni).

## Regole di condotta

1. Non si cambiano parametri a journal avviato.
2. Non si usa il semaforo "a metà" per giustificare modifiche.
3. Nuove idee nate guardando i dati (es. comprare l'indice nei giorni di
   panico) sono ipotesi nuove: si registrano come gruppo di confronto e si
   valutano in avanti, non si adottano perché il backtest le premia.
