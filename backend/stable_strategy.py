"""
Motore di backtest UNIFICATO della strategia STABLE (Stable Slope).

Questa è l'UNICA implementazione di riferimento della strategia. La replica
JavaScript (frontend/stable_engine.js) DEVE restare speculare: la parità è
verificata da tests/test_js_py_parity.py. Se modifichi la semantica qui,
aggiorna anche il file JS e fai girare i test.

Semantica (condivisa da Strategia 5 in main.py, STABLE Lab e email scanner):
- il segnale è valutato sul close della barra j; l'ESECUZIONE avviene al
  close della barra j + execution_lag (default 1 = "decido stasera,
  eseguo domani"). execution_lag=0 riproduce il vecchio comportamento
  same-bar (ottimista).
- LONG:  entry se slope > entry_th, exit se slope < exit_th
- SHORT: entry se slope < -entry_th, exit se slope > -exit_th
  (soglie SPECULARI: entry_th=0.3 -> lo short entra sotto -0.3)
- BOTH:  leg LONG e SHORT indipendenti in parallelo, capitale condiviso
- costi: cost_pct in percento PER LATO (0.05 = 0.05% a entrare, idem a uscire)
- win_rate / avg_trade / profit_factor calcolati SOLO sui trade chiusi
"""


def potential_discharge_positions(prices, pot_raw, F_vals,
                                  entry_z=2.0, horizon=21,
                                  zwin=252, min_periods=40):
    """
    Serie di POSIZIONE DESIDERATA (0/1) della strategia "scarico del
    potenziale" — la linea arancione resa regola operativa.

    Onset (tutto causale): lo z-score rolling del potenziale attraversa
    entry_z dal basso E il prezzo è SOTTO il fondamentale F (dislocazione
    al ribasso). Dall'onset la posizione resta 1 per `horizon` barre; un
    nuovo onset durante l'holding estende la finestra.

    Evidenza (event study 2026-07-05, 16 ticker 2022-2026): dopo questi
    onset il ritorno a 10 gg è ~4x la baseline; gli spike con prezzo sopra
    F non hanno edge, per questo il filtro direzionale.

    Returns: (positions list[0/1], n_onsets)
    """
    import pandas as pd

    n = len(prices)
    s = pd.Series(pot_raw, dtype=float)
    mean = s.rolling(zwin, min_periods=min_periods).mean()
    std = s.rolling(zwin, min_periods=min_periods).std()
    z = ((s - mean) / (std + 1e-9)).fillna(0).values

    positions = [0] * n
    last_onset = None
    n_onsets = 0
    for t in range(1, n):
        price = prices[t]
        f = F_vals[t] if t < len(F_vals) else None
        onset = (z[t] > entry_z and z[t - 1] <= entry_z
                 and price is not None and f is not None and price < f)
        if onset:
            last_onset = t
            n_onsets += 1
        if last_onset is not None and t - last_onset < horizon:
            positions[t] = 1
    return positions, n_onsets


def backtest_potential_discharge(dates, prices, pot_raw, F_vals,
                                 entry_z=2.0, horizon=21,
                                 execution_lag=1, cost_pct=0.0,
                                 initial_capital=1000.0,
                                 start_date=None, end_date=None,
                                 zwin=252, min_periods=40):
    """
    Backtest della strategia "scarico del potenziale" usando il motore
    unificato come esecutore: la serie di posizione desiderata viene
    convertita in pseudo-slope (pos−0.5) con soglie 0.4/0.0, così esecuzione
    t+1, costi, equity e stats sono ESATTAMENTE quelli di backtest_stable.
    """
    positions, n_onsets = potential_discharge_positions(
        prices, pot_raw, F_vals, entry_z=entry_z, horizon=horizon,
        zwin=zwin, min_periods=min_periods)

    pseudo_slope = [p - 0.5 for p in positions]
    res = backtest_stable(dates, prices, pseudo_slope, mode="LONG",
                          entry_th=0.4, exit_th=0.0,
                          execution_lag=execution_lag, cost_pct=cost_pct,
                          initial_capital=initial_capital,
                          start_date=start_date, end_date=end_date)
    res["n_onsets"] = n_onsets
    return res


def combo_positions(slopes, entry_th, exit_th, discharge_pos):
    """
    Posizione desiderata della strategia COMBO:
    leg TREND con isteresi (entry slope > entry_th, exit slope < exit_th)
    in OR con il leg SATELLITE (scarico del potenziale).
    Il satellite entra tipicamente proprio quando il trend è fuori
    (durante i panici lo slope è negativo): i due leg sono complementari.
    """
    n = len(slopes)
    pos = [0] * n
    in_trend = False
    for t in range(n):
        s = slopes[t]
        if s is not None:
            if (not in_trend) and s > entry_th:
                in_trend = True
            elif in_trend and s < exit_th:
                in_trend = False
        d = discharge_pos[t] if t < len(discharge_pos) else 0
        pos[t] = 1 if (in_trend or d) else 0
    return pos


def backtest_combo(dates, prices, slopes, pot_raw, F_vals,
                   entry_th=0.0, exit_th=0.0,
                   entry_z=2.0, horizon=21,
                   execution_lag=1, cost_pct=0.0,
                   initial_capital=1000.0,
                   start_date=None, end_date=None,
                   zwin=252, min_periods=40):
    """
    Backtest COMBO = STABLE (trend, core) + Scarico del Potenziale
    (satellite, alpha nei panici). Evidenza OOS 2026-07-05: Sharpe
    0.33 -> 0.44 vs trend da solo, drawdown invariato, robusto su tutta
    la griglia (entry_z, horizon).

    Come per il satellite, la posizione desiderata viene convertita in
    pseudo-slope ed eseguita dal motore unificato: esecuzione t+1, costi,
    equity e stats identici a backtest_stable.
    """
    d_pos, n_onsets = potential_discharge_positions(
        prices, pot_raw, F_vals, entry_z=entry_z, horizon=horizon,
        zwin=zwin, min_periods=min_periods)
    pos = combo_positions(slopes, entry_th, exit_th, d_pos)

    pseudo_slope = [p - 0.5 for p in pos]
    res = backtest_stable(dates, prices, pseudo_slope, mode="LONG",
                          entry_th=0.4, exit_th=0.0,
                          execution_lag=execution_lag, cost_pct=cost_pct,
                          initial_capital=initial_capital,
                          start_date=start_date, end_date=end_date)
    res["n_onsets"] = n_onsets
    return res


def _pnl_frac(direction, entry, exit_price, c):
    """Frazione di P/L con costi per lato (c = cost_pct/100)."""
    if direction == "LONG":
        return (exit_price * (1 - c) - entry * (1 + c)) / (entry * (1 + c))
    # SHORT: vendo a entry*(1-c), ricompro a exit*(1+c), nozionale entry
    return (entry * (1 - c) - exit_price * (1 + c)) / entry


def backtest_stable(dates, prices, slopes, mode="LONG",
                    entry_th=0.0, exit_th=0.0,
                    execution_lag=1, cost_pct=0.0,
                    initial_capital=1000.0,
                    start_date=None, end_date=None):
    """
    Returns dict:
      equity_curve     : % vs capitale iniziale, mark-to-market, len == len(dates)
      trade_pnl_curve  : P/L % delle posizioni aperte (0 quando flat)
      trades           : lista trade (exit_date == 'OPEN' se ancora aperto)
      skipped_trades   : [] (compatibilità con backtest_strategy)
      signal_events    : eventi ENTRY/EXIT, inclusi PENDENTI (exec_date None)
      stats            : final_capital, total_return, win_rate, total_trades,
                         avg_trade_pct, avg_trade, max_drawdown, profit_factor,
                         wins, losses, exposure_pct, sharpe, buy_hold_return
    """
    n = len(dates)
    lag = int(execution_lag)
    c = float(cost_pct) / 100.0
    capital = float(initial_capital)

    use_long = mode in ("LONG", "BOTH")
    use_short = mode in ("SHORT", "BOTH")

    def in_range(idx):
        d = dates[idx]
        if d is None:
            return False
        if start_date is not None and d < start_date:
            return False
        if end_date is not None and d > end_date:
            return False
        return True

    legs = {
        "LONG": {"in": False, "entry_price": 0.0, "entry_date": None},
        "SHORT": {"in": False, "entry_price": 0.0, "entry_date": None},
    }

    trades = []
    signal_events = []
    equity_curve = []
    trade_pnl_curve = []

    peak_capital = capital
    max_dd = 0.0
    exposure_bars = 0
    active_bars = 0
    mtm_series = []          # capitale mark-to-market per barra attiva (per Sharpe)
    first_price = None
    last_price_in_range = None

    def mtm_capital(price):
        """Capitale corrente con posizioni aperte marcate al prezzo dato."""
        cap = capital
        for direction in ("LONG", "SHORT"):
            leg = legs[direction]
            if leg["in"]:
                cap *= (1.0 + _pnl_frac(direction, leg["entry_price"], price, c))
        return cap

    for i in range(n):
        active = in_range(i)
        price = prices[i] if i < len(prices) else None

        if not active or price is None:
            equity_curve.append(equity_curve[-1] if equity_curve else 0.0)
            trade_pnl_curve.append(0.0)
            continue

        active_bars += 1
        if first_price is None:
            first_price = price
        last_price_in_range = price

        # --- Decisione sulla barra j = i - lag, esecuzione su questa barra ---
        j = i - lag
        if j >= 0 and in_range(j) and j < len(slopes) and slopes[j] is not None:
            s = slopes[j]

            # LONG leg
            if use_long:
                leg = legs["LONG"]
                if leg["in"] and s < exit_th:
                    pnl = _pnl_frac("LONG", leg["entry_price"], price, c)
                    capital *= (1.0 + pnl)
                    trades.append({
                        "entry_date": leg["entry_date"], "exit_date": dates[i],
                        "direction": "LONG",
                        "entry_price": round(leg["entry_price"], 2),
                        "exit_price": round(price, 2),
                        "pnl_pct": round(pnl * 100, 2),
                        "capital_after": round(capital, 2),
                        "entry_z_value": 0, "entry_z_roc": 0,
                    })
                    signal_events.append({
                        "type": "EXIT", "direction": "LONG",
                        "signal_date": dates[j], "signal_index": j,
                        "exec_date": dates[i], "exec_index": i,
                        "price_at_signal": prices[j], "slope_at_signal": s,
                    })
                    leg["in"] = False
                elif (not leg["in"]) and s > entry_th:
                    leg["in"] = True
                    leg["entry_price"] = price
                    leg["entry_date"] = dates[i]
                    signal_events.append({
                        "type": "ENTRY", "direction": "LONG",
                        "signal_date": dates[j], "signal_index": j,
                        "exec_date": dates[i], "exec_index": i,
                        "price_at_signal": prices[j], "slope_at_signal": s,
                    })

            # SHORT leg (soglie speculari)
            if use_short:
                leg = legs["SHORT"]
                if leg["in"] and s > -exit_th:
                    pnl = _pnl_frac("SHORT", leg["entry_price"], price, c)
                    capital *= (1.0 + pnl)
                    trades.append({
                        "entry_date": leg["entry_date"], "exit_date": dates[i],
                        "direction": "SHORT",
                        "entry_price": round(leg["entry_price"], 2),
                        "exit_price": round(price, 2),
                        "pnl_pct": round(pnl * 100, 2),
                        "capital_after": round(capital, 2),
                        "entry_z_value": 0, "entry_z_roc": 0,
                    })
                    signal_events.append({
                        "type": "EXIT", "direction": "SHORT",
                        "signal_date": dates[j], "signal_index": j,
                        "exec_date": dates[i], "exec_index": i,
                        "price_at_signal": prices[j], "slope_at_signal": s,
                    })
                    leg["in"] = False
                elif (not leg["in"]) and s < -entry_th:
                    leg["in"] = True
                    leg["entry_price"] = price
                    leg["entry_date"] = dates[i]
                    signal_events.append({
                        "type": "ENTRY", "direction": "SHORT",
                        "signal_date": dates[j], "signal_index": j,
                        "exec_date": dates[i], "exec_index": i,
                        "price_at_signal": prices[j], "slope_at_signal": s,
                    })

        # --- Mark-to-market di fine barra ---
        cap_now = mtm_capital(price)
        mtm_series.append(cap_now)
        eq_pct = (cap_now - initial_capital) / initial_capital * 100.0
        equity_curve.append(round(eq_pct, 2))

        open_pnl = 0.0
        any_open = False
        for direction in ("LONG", "SHORT"):
            leg = legs[direction]
            if leg["in"]:
                any_open = True
                open_pnl += _pnl_frac(direction, leg["entry_price"], price, c) * 100.0
        trade_pnl_curve.append(round(open_pnl, 2))
        if any_open:
            exposure_bars += 1

        if cap_now > peak_capital:
            peak_capital = cap_now
        dd = (peak_capital - cap_now) / peak_capital * 100.0
        if dd > max_dd:
            max_dd = dd

    # --- Segnali PENDENTI: decisione presa ma barra di esecuzione non ancora
    # disponibile (es. segnale sull'ultima barra, esecuzione "domani") ---
    pending_logged = {"LONG": False, "SHORT": False}
    for j in range(max(0, n - lag), n):
        if not in_range(j) or j >= len(slopes) or slopes[j] is None:
            continue
        s = slopes[j]
        if use_long and not pending_logged["LONG"]:
            leg = legs["LONG"]
            if leg["in"] and s < exit_th:
                signal_events.append({
                    "type": "EXIT", "direction": "LONG",
                    "signal_date": dates[j], "signal_index": j,
                    "exec_date": None, "exec_index": None,
                    "price_at_signal": prices[j], "slope_at_signal": s,
                })
                pending_logged["LONG"] = True
            elif (not leg["in"]) and s > entry_th:
                signal_events.append({
                    "type": "ENTRY", "direction": "LONG",
                    "signal_date": dates[j], "signal_index": j,
                    "exec_date": None, "exec_index": None,
                    "price_at_signal": prices[j], "slope_at_signal": s,
                })
                pending_logged["LONG"] = True
        if use_short and not pending_logged["SHORT"]:
            leg = legs["SHORT"]
            if leg["in"] and s > -exit_th:
                signal_events.append({
                    "type": "EXIT", "direction": "SHORT",
                    "signal_date": dates[j], "signal_index": j,
                    "exec_date": None, "exec_index": None,
                    "price_at_signal": prices[j], "slope_at_signal": s,
                })
                pending_logged["SHORT"] = True
            elif (not leg["in"]) and s < -entry_th:
                signal_events.append({
                    "type": "ENTRY", "direction": "SHORT",
                    "signal_date": dates[j], "signal_index": j,
                    "exec_date": None, "exec_index": None,
                    "price_at_signal": prices[j], "slope_at_signal": s,
                })
                pending_logged["SHORT"] = True

    # --- Posizioni ancora aperte: riga OPEN (mark-to-market, esclusa dalle stats) ---
    final_capital = capital
    if last_price_in_range is not None:
        for direction in ("LONG", "SHORT"):
            leg = legs[direction]
            if leg["in"]:
                pnl = _pnl_frac(direction, leg["entry_price"], last_price_in_range, c)
                final_capital *= (1.0 + pnl)
                trades.append({
                    "entry_date": leg["entry_date"], "exit_date": "OPEN",
                    "direction": direction,
                    "entry_price": round(leg["entry_price"], 2),
                    "exit_price": round(last_price_in_range, 2),
                    "pnl_pct": round(pnl * 100, 2),
                    "capital_after": round(final_capital, 2),
                    "entry_z_value": 0, "entry_z_roc": 0,
                })

    # --- Stats (solo trade CHIUSI per win rate / avg / profit factor) ---
    closed = [t for t in trades if t["exit_date"] != "OPEN"]
    wins = sum(1 for t in closed if t["pnl_pct"] > 0)
    losses = len(closed) - wins
    win_pnl = sum(t["pnl_pct"] for t in closed if t["pnl_pct"] > 0)
    loss_pnl = abs(sum(t["pnl_pct"] for t in closed if t["pnl_pct"] <= 0))
    total_return = (final_capital - initial_capital) / initial_capital * 100.0

    if loss_pnl > 0:
        profit_factor = round(win_pnl / loss_pnl, 2)
    else:
        profit_factor = 999 if win_pnl > 0 else 0

    # Sharpe annualizzato sui rendimenti giornalieri mark-to-market
    sharpe = 0.0
    if len(mtm_series) >= 3:
        rets = []
        for k in range(1, len(mtm_series)):
            prev = mtm_series[k - 1]
            if prev > 0:
                rets.append(mtm_series[k] / prev - 1.0)
        if len(rets) >= 2:
            mean_r = sum(rets) / len(rets)
            var_r = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
            std_r = var_r ** 0.5
            if std_r > 1e-12:
                sharpe = round(mean_r / std_r * (252 ** 0.5), 2)

    buy_hold = 0.0
    if first_price and last_price_in_range and first_price > 0:
        buy_hold = round((last_price_in_range / first_price - 1.0) * 100.0, 2)

    exposure_pct = round(exposure_bars / active_bars * 100.0, 1) if active_bars else 0.0
    avg_trade = round(sum(t["pnl_pct"] for t in closed) / len(closed), 2) if closed else 0

    stats = {
        "final_capital": round(final_capital, 2),
        "total_return": round(total_return, 2),
        "win_rate": round(wins / len(closed) * 100.0, 1) if closed else 0,
        "total_trades": len(closed),
        "avg_trade_pct": avg_trade,
        "avg_trade": avg_trade,
        "max_drawdown": round(max_dd, 2),
        "profit_factor": profit_factor,
        "wins": wins,
        "losses": losses,
        "exposure_pct": exposure_pct,
        "sharpe": sharpe,
        "buy_hold_return": buy_hold,
    }

    return {
        "equity_curve": equity_curve,
        "trade_pnl_curve": trade_pnl_curve,
        "trades": trades,
        "skipped_trades": [],
        "signal_events": signal_events,
        "stats": stats,
    }
