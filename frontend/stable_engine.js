// ============================================================
//  STABLE Engine (JS) — replica SPECULARE di backend/stable_strategy.py
//
//  ATTENZIONE: questa NON è l'implementazione di riferimento.
//  La fonte di verità è backend/stable_strategy.py; la parità è
//  verificata da backend/tests/test_js_py_parity.py (node).
//  Se cambi la semantica qui o nel Python, aggiorna entrambi e
//  fai girare il test di parità.
//
//  Semantica condivisa:
//  - segnale valutato sulla barra j, ESECUZIONE al close della barra
//    j + executionLag (default 1 = decido stasera, eseguo domani)
//  - LONG:  entry slope > entryTh,  exit slope < exitTh
//  - SHORT: entry slope < -entryTh, exit slope > -exitTh (soglie speculari)
//  - BOTH:  due leg indipendenti in parallelo, capitale condiviso
//  - costPct: costo % PER LATO; win rate solo sui trade CHIUSI
// ============================================================

function _stablePnlFrac(direction, entry, exitPrice, c) {
    if (direction === 'LONG') {
        return (exitPrice * (1 - c) - entry * (1 + c)) / (entry * (1 + c));
    }
    return (entry * (1 - c) - exitPrice * (1 + c)) / entry;
}

function _round2(x) { return Math.round((x + Number.EPSILON) * 100) / 100; }
function _round1(x) { return Math.round((x + Number.EPSILON) * 10) / 10; }

function backtestStable(dates, prices, slopes, opts) {
    opts = opts || {};
    const mode = opts.mode || 'LONG';
    const entryTh = opts.entryTh != null ? opts.entryTh : 0.0;
    const exitTh = opts.exitTh != null ? opts.exitTh : 0.0;
    const lag = opts.executionLag != null ? opts.executionLag : 1;
    const c = (opts.costPct || 0) / 100.0;
    const initialCapital = opts.initialCapital || 1000.0;
    const startDate = opts.startDate || null;
    const endDate = opts.endDate || null;

    const n = dates.length;
    let capital = initialCapital;

    const useLong = (mode === 'LONG' || mode === 'BOTH');
    const useShort = (mode === 'SHORT' || mode === 'BOTH');

    function inRange(idx) {
        const d = dates[idx];
        if (d == null) return false;
        if (startDate != null && d < startDate) return false;
        if (endDate != null && d > endDate) return false;
        return true;
    }

    const legs = {
        LONG: { in: false, entryPrice: 0, entryDate: null },
        SHORT: { in: false, entryPrice: 0, entryDate: null },
    };

    const trades = [];
    const signalEvents = [];
    const equityCurve = [];
    const tradePnlCurve = [];

    let peakCapital = capital;
    let maxDD = 0;
    let exposureBars = 0;
    let activeBars = 0;
    const mtmSeries = [];
    let firstPrice = null;
    let lastPriceInRange = null;

    function mtmCapital(price) {
        let cap = capital;
        for (const direction of ['LONG', 'SHORT']) {
            const leg = legs[direction];
            if (leg.in) cap *= (1 + _stablePnlFrac(direction, leg.entryPrice, price, c));
        }
        return cap;
    }

    for (let i = 0; i < n; i++) {
        const active = inRange(i);
        const price = i < prices.length ? prices[i] : null;

        if (!active || price == null) {
            equityCurve.push(equityCurve.length ? equityCurve[equityCurve.length - 1] : 0);
            tradePnlCurve.push(0);
            continue;
        }

        activeBars++;
        if (firstPrice == null) firstPrice = price;
        lastPriceInRange = price;

        // --- Decisione sulla barra j = i - lag, esecuzione su questa barra ---
        const j = i - lag;
        if (j >= 0 && inRange(j) && j < slopes.length && slopes[j] != null) {
            const s = slopes[j];

            if (useLong) {
                const leg = legs.LONG;
                if (leg.in && s < exitTh) {
                    const pnl = _stablePnlFrac('LONG', leg.entryPrice, price, c);
                    capital *= (1 + pnl);
                    trades.push({
                        entry_date: leg.entryDate, exit_date: dates[i],
                        direction: 'LONG',
                        entry_price: _round2(leg.entryPrice),
                        exit_price: _round2(price),
                        pnl_pct: _round2(pnl * 100),
                        capital_after: _round2(capital),
                        entry_z_value: 0, entry_z_roc: 0,
                    });
                    signalEvents.push({
                        type: 'EXIT', direction: 'LONG',
                        signal_date: dates[j], signal_index: j,
                        exec_date: dates[i], exec_index: i,
                        price_at_signal: prices[j], slope_at_signal: s,
                    });
                    leg.in = false;
                } else if (!leg.in && s > entryTh) {
                    leg.in = true;
                    leg.entryPrice = price;
                    leg.entryDate = dates[i];
                    signalEvents.push({
                        type: 'ENTRY', direction: 'LONG',
                        signal_date: dates[j], signal_index: j,
                        exec_date: dates[i], exec_index: i,
                        price_at_signal: prices[j], slope_at_signal: s,
                    });
                }
            }

            if (useShort) {
                const leg = legs.SHORT;
                if (leg.in && s > -exitTh) {
                    const pnl = _stablePnlFrac('SHORT', leg.entryPrice, price, c);
                    capital *= (1 + pnl);
                    trades.push({
                        entry_date: leg.entryDate, exit_date: dates[i],
                        direction: 'SHORT',
                        entry_price: _round2(leg.entryPrice),
                        exit_price: _round2(price),
                        pnl_pct: _round2(pnl * 100),
                        capital_after: _round2(capital),
                        entry_z_value: 0, entry_z_roc: 0,
                    });
                    signalEvents.push({
                        type: 'EXIT', direction: 'SHORT',
                        signal_date: dates[j], signal_index: j,
                        exec_date: dates[i], exec_index: i,
                        price_at_signal: prices[j], slope_at_signal: s,
                    });
                    leg.in = false;
                } else if (!leg.in && s < -entryTh) {
                    leg.in = true;
                    leg.entryPrice = price;
                    leg.entryDate = dates[i];
                    signalEvents.push({
                        type: 'ENTRY', direction: 'SHORT',
                        signal_date: dates[j], signal_index: j,
                        exec_date: dates[i], exec_index: i,
                        price_at_signal: prices[j], slope_at_signal: s,
                    });
                }
            }
        }

        // --- Mark-to-market di fine barra ---
        const capNow = mtmCapital(price);
        mtmSeries.push(capNow);
        equityCurve.push(_round2((capNow - initialCapital) / initialCapital * 100));

        let openPnl = 0;
        let anyOpen = false;
        for (const direction of ['LONG', 'SHORT']) {
            const leg = legs[direction];
            if (leg.in) {
                anyOpen = true;
                openPnl += _stablePnlFrac(direction, leg.entryPrice, price, c) * 100;
            }
        }
        tradePnlCurve.push(_round2(openPnl));
        if (anyOpen) exposureBars++;

        if (capNow > peakCapital) peakCapital = capNow;
        const dd = (peakCapital - capNow) / peakCapital * 100;
        if (dd > maxDD) maxDD = dd;
    }

    // --- Segnali PENDENTI (esecuzione oltre la fine dei dati) ---
    const pendingLogged = { LONG: false, SHORT: false };
    for (let j = Math.max(0, n - lag); j < n; j++) {
        if (!inRange(j) || j >= slopes.length || slopes[j] == null) continue;
        const s = slopes[j];
        if (useLong && !pendingLogged.LONG) {
            const leg = legs.LONG;
            if (leg.in && s < exitTh) {
                signalEvents.push({ type: 'EXIT', direction: 'LONG',
                    signal_date: dates[j], signal_index: j,
                    exec_date: null, exec_index: null,
                    price_at_signal: prices[j], slope_at_signal: s });
                pendingLogged.LONG = true;
            } else if (!leg.in && s > entryTh) {
                signalEvents.push({ type: 'ENTRY', direction: 'LONG',
                    signal_date: dates[j], signal_index: j,
                    exec_date: null, exec_index: null,
                    price_at_signal: prices[j], slope_at_signal: s });
                pendingLogged.LONG = true;
            }
        }
        if (useShort && !pendingLogged.SHORT) {
            const leg = legs.SHORT;
            if (leg.in && s > -exitTh) {
                signalEvents.push({ type: 'EXIT', direction: 'SHORT',
                    signal_date: dates[j], signal_index: j,
                    exec_date: null, exec_index: null,
                    price_at_signal: prices[j], slope_at_signal: s });
                pendingLogged.SHORT = true;
            } else if (!leg.in && s < -entryTh) {
                signalEvents.push({ type: 'ENTRY', direction: 'SHORT',
                    signal_date: dates[j], signal_index: j,
                    exec_date: null, exec_index: null,
                    price_at_signal: prices[j], slope_at_signal: s });
                pendingLogged.SHORT = true;
            }
        }
    }

    // --- Posizioni aperte a fine periodo (riga OPEN, escluse dalle stats) ---
    let finalCapital = capital;
    if (lastPriceInRange != null) {
        for (const direction of ['LONG', 'SHORT']) {
            const leg = legs[direction];
            if (leg.in) {
                const pnl = _stablePnlFrac(direction, leg.entryPrice, lastPriceInRange, c);
                finalCapital *= (1 + pnl);
                trades.push({
                    entry_date: leg.entryDate, exit_date: 'OPEN',
                    direction: direction,
                    entry_price: _round2(leg.entryPrice),
                    exit_price: _round2(lastPriceInRange),
                    pnl_pct: _round2(pnl * 100),
                    capital_after: _round2(finalCapital),
                    entry_z_value: 0, entry_z_roc: 0,
                });
            }
        }
    }

    // --- Stats (solo trade CHIUSI per win rate / avg / profit factor) ---
    const closed = trades.filter(t => t.exit_date !== 'OPEN');
    const wins = closed.filter(t => t.pnl_pct > 0).length;
    const losses = closed.length - wins;
    const winPnl = closed.filter(t => t.pnl_pct > 0).reduce((a, t) => a + t.pnl_pct, 0);
    const lossPnl = Math.abs(closed.filter(t => t.pnl_pct <= 0).reduce((a, t) => a + t.pnl_pct, 0));
    const totalReturn = (finalCapital - initialCapital) / initialCapital * 100;

    let profitFactor;
    if (lossPnl > 0) profitFactor = _round2(winPnl / lossPnl);
    else profitFactor = winPnl > 0 ? 999 : 0;

    let sharpe = 0;
    if (mtmSeries.length >= 3) {
        const rets = [];
        for (let k = 1; k < mtmSeries.length; k++) {
            if (mtmSeries[k - 1] > 0) rets.push(mtmSeries[k] / mtmSeries[k - 1] - 1);
        }
        if (rets.length >= 2) {
            const meanR = rets.reduce((a, b) => a + b, 0) / rets.length;
            const varR = rets.reduce((a, b) => a + (b - meanR) ** 2, 0) / (rets.length - 1);
            const stdR = Math.sqrt(varR);
            if (stdR > 1e-12) sharpe = _round2(meanR / stdR * Math.sqrt(252));
        }
    }

    let buyHold = 0;
    if (firstPrice && lastPriceInRange && firstPrice > 0) {
        buyHold = _round2((lastPriceInRange / firstPrice - 1) * 100);
    }

    const exposurePct = activeBars ? _round1(exposureBars / activeBars * 100) : 0;
    const avgTrade = closed.length
        ? _round2(closed.reduce((a, t) => a + t.pnl_pct, 0) / closed.length) : 0;

    const stats = {
        final_capital: _round2(finalCapital),
        total_return: _round2(totalReturn),
        win_rate: closed.length ? _round1(wins / closed.length * 100) : 0,
        total_trades: closed.length,
        avg_trade_pct: avgTrade,
        avg_trade: avgTrade,
        max_drawdown: _round2(maxDD),
        profit_factor: profitFactor,
        wins: wins,
        losses: losses,
        exposure_pct: exposurePct,
        sharpe: sharpe,
        buy_hold_return: buyHold,
    };

    return {
        equity_curve: equityCurve,
        trade_pnl_curve: tradePnlCurve,
        trades: trades,
        skipped_trades: [],
        signal_events: signalEvents,
        stats: stats,
    };
}

// ============================================================
//  SCARICO DEL POTENZIALE (linea arancione) + COMBO
//  Mirror di stable_strategy.py: potential_discharge_positions,
//  combo_positions, backtest_potential_discharge, backtest_combo.
//  Parità garantita da backend/tests/test_js_py_parity.py.
// ============================================================

// Rolling z-score con semantica pandas: i NaN/null vengono SALTATI,
// min_periods conta solo i valori validi, std con ddof=1.
function _rollingZ(values, win, minPeriods) {
    const n = values.length;
    const z = new Array(n).fill(0);
    for (let t = 0; t < n; t++) {
        const lo = Math.max(0, t - win + 1);
        let cnt = 0, sum = 0;
        for (let i = lo; i <= t; i++) {
            const v = values[i];
            if (v != null && Number.isFinite(v)) { cnt++; sum += v; }
        }
        const cur = values[t];
        if (cnt < minPeriods || cur == null || !Number.isFinite(cur)) continue;
        const mean = sum / cnt;
        let ss = 0;
        for (let i = lo; i <= t; i++) {
            const v = values[i];
            if (v != null && Number.isFinite(v)) ss += (v - mean) * (v - mean);
        }
        const std = cnt > 1 ? Math.sqrt(ss / (cnt - 1)) : 0;
        z[t] = (cur - mean) / (std + 1e-9);
    }
    return z;
}

function potentialDischargePositions(prices, potRaw, Fvals, entryZ, horizon, zwin, minPeriods) {
    zwin = zwin || 252;
    minPeriods = minPeriods || 40;
    const n = prices.length;
    const z = _rollingZ(potRaw, zwin, minPeriods);
    const pos = new Array(n).fill(0);
    let lastOnset = null, nOnsets = 0;
    for (let t = 1; t < n; t++) {
        const price = prices[t];
        const f = t < Fvals.length ? Fvals[t] : null;
        const onset = (z[t] > entryZ && z[t - 1] <= entryZ
                       && price != null && f != null && price < f);
        if (onset) { lastOnset = t; nOnsets++; }
        if (lastOnset !== null && t - lastOnset < horizon) pos[t] = 1;
    }
    return { positions: pos, nOnsets: nOnsets };
}

function comboPositions(slopes, entryTh, exitTh, dischargePos) {
    const n = slopes.length;
    const pos = new Array(n).fill(0);
    let inTrend = false;
    for (let t = 0; t < n; t++) {
        const s = slopes[t];
        if (s != null) {
            if (!inTrend && s > entryTh) inTrend = true;
            else if (inTrend && s < exitTh) inTrend = false;
        }
        const d = t < dischargePos.length ? dischargePos[t] : 0;
        pos[t] = (inTrend || d) ? 1 : 0;
    }
    return pos;
}

function _runPositions(dates, prices, positions, opts) {
    const pseudo = positions.map(p => p - 0.5);
    return backtestStable(dates, prices, pseudo, {
        mode: 'LONG', entryTh: 0.4, exitTh: 0.0,
        executionLag: opts.executionLag != null ? opts.executionLag : 1,
        costPct: opts.costPct || 0,
        initialCapital: opts.initialCapital || 1000,
        startDate: opts.startDate || null,
        endDate: opts.endDate || null,
    });
}

function backtestPotentialDischarge(dates, prices, potRaw, Fvals, opts) {
    opts = opts || {};
    const d = potentialDischargePositions(prices, potRaw, Fvals,
        opts.entryZ != null ? opts.entryZ : 2.0,
        opts.horizon != null ? opts.horizon : 21,
        opts.zwin, opts.minPeriods);
    const res = _runPositions(dates, prices, d.positions, opts);
    res.n_onsets = d.nOnsets;
    res.equity = res.equity_curve;
    return res;
}

function backtestCombo(dates, prices, slopes, potRaw, Fvals, opts) {
    opts = opts || {};
    const d = potentialDischargePositions(prices, potRaw, Fvals,
        opts.entryZ != null ? opts.entryZ : 2.0,
        opts.horizon != null ? opts.horizon : 21,
        opts.zwin, opts.minPeriods);
    const pos = comboPositions(slopes,
        opts.entryTh != null ? opts.entryTh : 0.0,
        opts.exitTh != null ? opts.exitTh : 0.0,
        d.positions);
    const res = _runPositions(dates, prices, pos, opts);
    res.n_onsets = d.nOnsets;
    res.equity = res.equity_curve;
    return res;
}

// Compat: alias storico usato dal Lab ("equity" oltre a "equity_curve")
function backtestStableCompat(dates, prices, slopes, opts) {
    const res = backtestStable(dates, prices, slopes, opts);
    res.equity = res.equity_curve;
    return res;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { backtestStable, backtestStableCompat,
                       potentialDischargePositions, comboPositions,
                       backtestPotentialDischarge, backtestCombo };
}
