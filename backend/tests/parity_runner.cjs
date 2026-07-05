#!/usr/bin/env node
/**
 * Runner per il test di parità Python <-> JavaScript del motore STABLE.
 * Legge una fixture JSON {series, configs} da argv[1], esegue
 * frontend/stable_engine.js su ogni (serie, config) e stampa i risultati JSON.
 */
const path = require('path');
const fs = require('fs');

const enginePath = path.join(__dirname, '..', '..', 'frontend', 'stable_engine.js');
const { backtestStable, backtestPotentialDischarge, backtestCombo } = require(enginePath);

const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = [];

for (const run of fixture.runs) {
    const s = fixture.series[run.series];
    const opts = {
        mode: run.mode,
        entryTh: run.entry_th,
        exitTh: run.exit_th,
        entryZ: run.entry_z,
        horizon: run.horizon,
        executionLag: run.execution_lag,
        costPct: run.cost_pct,
        initialCapital: run.initial_capital,
        startDate: run.start_date || null,
        endDate: run.end_date || null,
    };
    let res;
    if (run.type === 'discharge') {
        res = backtestPotentialDischarge(s.dates, s.prices, s.pot, s.F, opts);
    } else if (run.type === 'combo') {
        res = backtestCombo(s.dates, s.prices, s.slopes, s.pot, s.F, opts);
    } else {
        res = backtestStable(s.dates, s.prices, s.slopes, opts);
    }
    out.push(res);
}

process.stdout.write(JSON.stringify(out));
