#!/usr/bin/env node
/**
 * Test per simulateSizing (stable_engine.js) — il simulatore di money
 * management del tab Forward: quota fissa (con/senza tetto) vs
 * reinvestimento % dell'equity.
 *
 * Esecuzione: node backend/tests/test_sizing_sim.cjs
 */
const path = require('path');
const { simulateSizing } = require(path.join(__dirname, '..', '..', 'frontend', 'stable_engine.js'));

function assert(cond, msg) {
    if (!cond) { console.error('FAIL:', msg); process.exit(1); }
}
function close(a, b, tol, msg) {
    assert(Math.abs(a - b) <= (tol || 0.01), `${msg} (${a} vs ${b})`);
}

// --- scenario 1: due trade sequenziali, reinvestimento compone ---
const seq = [
    { entry_date: '2026-01-05', exit_date: '2026-01-20', pnl_pct: 10 },
    { entry_date: '2026-02-02', exit_date: '2026-02-15', pnl_pct: 10 },
];
// quota fissa 10 su capitale 100: +1 +1 = 102
let r = simulateSizing(seq, { scheme: 'fixed', capital: 100, stakePct: 10, cap: 10 });
close(r.finalCapital, 102, 0.01, 'fixed: 2 trade da +10% con stake 10 -> 102');
assert(r.skipped === 0, 'fixed: nessun salto atteso');

// reinvestimento 10%: stake1=10 -> equity 101; stake2=10.1 -> +1.01 -> 102.01
r = simulateSizing(seq, { scheme: 'compound', capital: 100, stakePct: 10, cap: 10 });
close(r.finalCapital, 102.01, 0.01, 'compound: il secondo stake cresce');

// --- scenario 2: cluster di 3 trade simultanei con cap 2 -> 1 saltato ---
const cluster = [
    { entry_date: '2026-03-02', exit_date: '2026-03-20', pnl_pct: 5 },
    { entry_date: '2026-03-02', exit_date: '2026-03-20', pnl_pct: 5 },
    { entry_date: '2026-03-03', exit_date: '2026-03-21', pnl_pct: 5 },
];
r = simulateSizing(cluster, { scheme: 'fixed', capital: 100, stakePct: 10, cap: 2 });
assert(r.skipped === 1, `cap 2 su 3 simultanei deve saltarne 1 (saltati: ${r.skipped})`);
assert(r.maxConcurrent === 2, `maxConcurrent atteso 2: ${r.maxConcurrent}`);
close(r.finalCapital, 101, 0.01, 'fixed cap: 2 trade da +5% con stake 10 -> 101');

// senza cap (unlimited): tutti e 3 eseguiti anche oltre la cassa
r = simulateSizing(cluster, { scheme: 'fixed_unlimited', capital: 100, stakePct: 10 });
assert(r.skipped === 0, 'unlimited non salta nulla');
close(r.finalCapital, 101.5, 0.01, 'unlimited: 3 trade da +5% stake 10 -> 101.5');
assert(r.maxConcurrent === 3, 'unlimited: 3 simultanei');

// --- scenario 3: perdita e drawdown sulla curva realizzata ---
const loss = [
    { entry_date: '2026-04-01', exit_date: '2026-04-10', pnl_pct: -20 },
    { entry_date: '2026-05-01', exit_date: '2026-05-10', pnl_pct: 10 },
];
r = simulateSizing(loss, { scheme: 'fixed', capital: 100, stakePct: 50, cap: 10 });
// stake 50: -10 -> 90; +5 -> 95. maxDD sulla curva = 10% dal picco 100
close(r.finalCapital, 95, 0.01, 'fixed: -20% e +10% su stake 50');
close(r.maxDD, 10, 0.05, 'maxDD atteso 10%');

// --- scenario 4: trade OPEN ignorati + curva con cassa/investito per evento ---
const withOpen = seq.concat([{ entry_date: '2026-06-01', exit_date: 'OPEN', pnl_pct: null }]);
r = simulateSizing(withOpen, { scheme: 'fixed', capital: 100, stakePct: 10, cap: 10 });
close(r.finalCapital, 102, 0.01, 'i trade OPEN non contano nel realizzato');

// curva: un punto per OGNI evento (entry e exit) con equity/cassa/investito
assert(r.curve.length === 4, `curva con 4 punti (2 entry + 2 exit): ${r.curve.length}`);
assert(r.curve[0].date === '2026-01-05', 'primo punto alla prima ENTRY');
close(r.curve[0].equity, 100, 0.01, 'entry1: equity invariata (posizione al costo)');
close(r.curve[0].cash, 90, 0.01, 'entry1: cassa 100-10');
close(r.curve[0].invested, 10, 0.01, 'entry1: investito 10');
close(r.curve[1].equity, 101, 0.01, 'exit1: equity 101');
close(r.curve[1].invested, 0, 0.01, 'exit1: investito 0');

console.log('OK test_sizing_sim — fixed/cap/compound/unlimited, cluster, DD, OPEN ignorati, curva cassa/investito');
