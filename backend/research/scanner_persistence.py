"""
Tre domande pratiche:

1. LO SCANNER MASSIVO HA SENSO? Lo scanner mostra, titolo per titolo, quanto
   ha reso ogni strategia nel passato. Serve a qualcosa solo se quel numero
   dice qualcosa sul futuro. Test: correlazione di rango tra il rendimento
   della strategia su un titolo nel TRAIN e nell'OOS, e risultato OOS dei
   titoli "migliori" secondo lo scanner.

2. TRA I SEGNALI ARANCIONI SI POSSONO SCEGLIERE I MIGLIORI? Nei giorni di
   panico i segnali sono più dei posti disponibili. Test: lo z del potenziale
   o la distanza del prezzo dal fondamentale prevedono il risultato?

3. I SEGNALI BATTONO IL CASO? Per ogni segnale, titoli presi a caso lo STESSO
   giorno con la stessa regola (ingresso t+1, uscita dopo 21 barre).
   È il confronto che il forward test replica dal vivo (gruppo di controllo).

    backend/venv/bin/python backend/research/scanner_persistence.py
"""
import random

from common import (np, pd, sample_universe, fetch_prices, orange_inputs, save_output,
                    tstat, week_key, COST, SEED)
from logic import backtest_strategy, kalman_frozen_series, causal_lowpass
from stable_strategy import (backtest_stable, backtest_potential_discharge,
                             POTENTIAL_ALPHA, POTENTIAL_BETA)

START = "2020-03-01"
FROM = "2021-01-01"
ENTRY_Z, HORIZON = 2.0, 21


def spearman(a, b):
    ra = pd.Series(a).rank().values
    rb = pd.Series(b).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


def zroll(values, min_periods=20):
    s = pd.Series(values, dtype=float)
    return ((s - s.rolling(252, min_periods=min_periods).mean())
            / (s.rolling(252, min_periods=min_periods).std() + 1e-6)).fillna(0)


def fixed_pnl(prices, exec_idx, horizon, c=COST / 100):
    """Regola del journal: ingresso al close di exec_idx, uscita dopo horizon barre."""
    x = exec_idx + horizon
    if exec_idx >= len(prices) or x >= len(prices):
        return None
    e, o = prices[exec_idx], prices[x]
    return ((o * (1 - c) - e * (1 + c)) / (e * (1 + c))) * 100


def main():
    sample, _ = sample_universe()
    prices = fetch_prices(sample, START, min_len=600)
    all_dates = sorted({d for px in prices.values() for d in px.index.strftime("%Y-%m-%d") if d >= FROM})
    split = all_dates[int(len(all_dates) * 0.6)]
    train_end = all_dates[int(len(all_dates) * 0.6) - 1]
    print(f"{len(prices)} ticker | train {FROM} → {train_end} | OOS {split} → {all_dates[-1]}")

    # ---------- 1. persistenza per titolo delle strategie dello scanner ----------
    rows = {"FROZEN": [], "SUM": [], "STABLE": []}
    series = {}
    for t, px in prices.items():
        dates, pr, pot, F = orange_inputs(px)
        series[t] = (dates, pr, pot, F)
        fr = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA,
                                  min_points=100, kin_lag=25)
        pad = len(pr) - len(fr["pot_last"])
        z_pot = zroll([0] * pad + [round(v, 2) for v in fr["pot_last"]]).tolist()
        z_sum_raw = zroll([k + p for k, p in zip(fr["kin_last"], fr["pot_last"])]).tolist()
        z_sum = [-999] * pad + [round(x, 2) for x in causal_lowpass(z_sum_raw)]
        slope = px.ewm(span=20, adjust=False).mean().diff().fillna(0).ewm(span=14, adjust=False).mean().values.tolist()
        zeros = [0] * len(pr)

        def bh(seg_start, seg_end):
            idx = [i for i, d in enumerate(dates) if seg_start <= d <= seg_end]
            return (pr[idx[-1]] / pr[idx[0]] - 1) * 100 if len(idx) > 1 else 0.0

        segs = {"train": (FROM, train_end), "oos": (split, all_dates[-1])}
        for name in rows:
            rec = {"ticker": t}
            for seg, (s, e) in segs.items():
                if name == "FROZEN":
                    r = backtest_strategy(prices=pr, z_kinetic=z_pot, z_slope=zeros, dates=dates,
                                          start_date=s, end_date=e, use_z_roc=True)["stats"]["total_return"]
                elif name == "SUM":
                    r = backtest_strategy(prices=pr, z_kinetic=z_sum, z_slope=zeros, dates=dates,
                                          start_date=s, end_date=e, threshold=-0.3,
                                          use_z_roc=True)["stats"]["total_return"]
                else:
                    r = backtest_stable(dates, pr, slope, mode="LONG", execution_lag=1, cost_pct=COST,
                                        start_date=s, end_date=e)["stats"]["total_return"]
                rec[f"roi_{seg}"] = r
                rec[f"bh_{seg}"] = bh(s, e)
            rows[name].append(rec)

    out = {"split": {"train_end": train_end, "oos_start": split}, "scanner": {}}
    print("\n=== 1. Lo scanner prevede? (per titolo: train → OOS) ===")
    print(f"{'strategia':8s} | corr rango ROI→ROI | corr rango ROI→eccesso su B&H | top 20% scanner: ROI OOS vs tutti | eccesso OOS top vs tutti")
    for name, rs in rows.items():
        tr = np.array([r["roi_train"] for r in rs]); oo = np.array([r["roi_oos"] for r in rs])
        ex = oo - np.array([r["bh_oos"] for r in rs])
        k = max(1, len(rs) // 5)
        top = np.argsort(-tr)[:k]
        res = {"spearman_roi_roi": round(spearman(tr, oo), 3),
               "spearman_roi_excess": round(spearman(tr, ex), 3),
               "top20_oos_roi": round(float(oo[top].mean()), 1), "all_oos_roi": round(float(oo.mean()), 1),
               "top20_oos_excess": round(float(ex[top].mean()), 1), "all_oos_excess": round(float(ex.mean()), 1),
               "pct_oos_beating_bh": round(float((ex > 0).mean() * 100), 1)}
        out["scanner"][name] = res
        print(f"{name:8s} | {res['spearman_roi_roi']:+.2f}              | {res['spearman_roi_excess']:+.2f}"
              f"                         | {res['top20_oos_roi']:+.1f}% vs {res['all_oos_roi']:+.1f}%"
              f"            | {res['top20_oos_excess']:+.1f} vs {res['all_oos_excess']:+.1f}"
              f"   (titoli che battono il B&H: {res['pct_oos_beating_bh']}%)")

    # ---------- 2 e 3. segnali arancioni: ranking e confronto col caso ----------
    signals = []     # (ticker, signal_date, exec_idx, z, depth_pct, pnl)
    idx_of = {t: {d: i for i, d in enumerate(s[0])} for t, s in series.items()}
    in_pos_dates = {t: set() for t in series}
    for t, (dates, pr, pot, F) in series.items():
        res = backtest_potential_discharge(dates, pr, pot, F, entry_z=ENTRY_Z, horizon=HORIZON,
                                           execution_lag=1, cost_pct=COST, start_date=FROM)
        z = zroll(pot, min_periods=40).tolist()
        for ev in res["signal_events"]:
            if ev["type"] != "ENTRY" or ev["exec_index"] is None:
                continue
            si, xi = ev["signal_index"], ev["exec_index"]
            pnl = fixed_pnl(pr, xi, HORIZON)
            if pnl is None:
                continue
            depth = (F[si] - pr[si]) / F[si] * 100
            signals.append((t, dates[si], xi, z[si], depth, pnl))
            for j in range(si, min(len(dates), xi + HORIZON + 1)):
                in_pos_dates[t].add(dates[j])

    pn = np.array([s[5] for s in signals]); zz = np.array([s[3] for s in signals]); dd = np.array([s[4] for s in signals])
    half = len(signals) // 2
    by_z = np.argsort(-zz); by_d = np.argsort(-dd)
    rank = {
        "n_signals": len(signals),
        "journal_rule_mean_pnl": round(float(pn.mean()), 2),
        "journal_rule_win_rate": round(float((pn > 0).mean() * 100), 1),
        "spearman_z_pnl": round(spearman(zz, pn), 3),
        "spearman_depth_pnl": round(spearman(dd, pn), 3),
        "mean_pnl_high_z": round(float(pn[by_z[:half]].mean()), 2), "mean_pnl_low_z": round(float(pn[by_z[half:]].mean()), 2),
        "mean_pnl_deep": round(float(pn[by_d[:half]].mean()), 2), "mean_pnl_shallow": round(float(pn[by_d[half:]].mean()), 2),
    }
    out["ranking"] = rank
    print(f"\n=== 2. Scegliere tra i segnali arancioni ({rank['n_signals']} segnali, regola del journal: 21 barre fisse) ===")
    print(f"media {rank['journal_rule_mean_pnl']:+}%/trade, win rate {rank['journal_rule_win_rate']}%")
    print(f"z più alto  → risultato migliore? corr rango {rank['spearman_z_pnl']:+.2f} | metà alta {rank['mean_pnl_high_z']:+}% vs metà bassa {rank['mean_pnl_low_z']:+}%")
    print(f"più sotto F → risultato migliore? corr rango {rank['spearman_depth_pnl']:+.2f} | metà profonda {rank['mean_pnl_deep']:+}% vs metà meno profonda {rank['mean_pnl_shallow']:+}%")

    rnd = random.Random(SEED)
    tickers = sorted(series)
    N_CTRL = 5
    week_sig, week_ctl, ctl_all = {}, {}, []
    for t, d, xi, _, _, pnl in signals:
        cands = [u for u in tickers if u != t and d in idx_of[u] and d not in in_pos_dates[u]]
        rnd.shuffle(cands)
        got = []
        for u in cands:
            ui = idx_of[u][d] + 1
            p = fixed_pnl(series[u][1], ui, HORIZON)
            if p is not None:
                got.append(p)
            if len(got) == N_CTRL:
                break
        if not got:
            continue
        w = week_key(d)
        week_sig.setdefault(w, []).append(pnl)
        week_ctl.setdefault(w, []).append(float(np.mean(got)))
        ctl_all.append(float(np.mean(got)))
    diffs = [np.mean(week_sig[w]) - np.mean(week_ctl[w]) for w in sorted(week_sig)]
    ctl = {
        "mean_signal": round(float(pn.mean()), 2), "mean_control": round(float(np.mean(ctl_all)), 2),
        "edge": round(float(pn.mean() - np.mean(ctl_all)), 2),
        "weekly_edge_mean": round(float(np.mean(diffs)), 2),
        "t_edge_clustered": round(tstat(diffs), 2), "n_weeks": len(diffs),
        "pct_weeks_signal_beats_control": round(float((np.array(diffs) > 0).mean() * 100), 1),
    }
    out["control"] = ctl
    print(f"\n=== 3. Segnali contro titoli a caso negli stessi giorni ===")
    print(f"segnali {ctl['mean_signal']:+}%/trade | controllo casuale {ctl['mean_control']:+}%/trade | differenza {ctl['edge']:+} punti")
    print(f"per settimana: differenza media {ctl['weekly_edge_mean']:+}, t {ctl['t_edge_clustered']} su {ctl['n_weeks']} settimane, "
          f"il segnale batte il controllo nel {ctl['pct_weeks_signal_beats_control']}% delle settimane")

    # ---------- 4. base incondizionata: un titolo qualsiasi in un giorno qualsiasi ----------
    base = []
    for t, (dates, pr, _, _) in series.items():
        i0 = next((i for i, x in enumerate(dates) if x >= FROM), 0)
        for xi in range(i0, len(pr) - HORIZON - 1, 5):
            p = fixed_pnl(pr, xi, HORIZON)
            if p is not None:
                base.append(p)
    base_mean = float(np.mean(base))
    wk_ctl_minus_base = [np.mean(week_ctl[w]) - base_mean for w in sorted(week_ctl)]
    wk_sig_minus_base = [np.mean(week_sig[w]) - base_mean for w in sorted(week_sig)]
    timing = {
        "baseline_any_day": round(base_mean, 2),
        "control_on_signal_days": ctl["mean_control"],
        "signals": ctl["mean_signal"],
        "timing_edge": round(ctl["mean_control"] - base_mean, 2),
        "t_timing_clustered": round(tstat(wk_ctl_minus_base), 2),
        "total_edge": round(ctl["mean_signal"] - base_mean, 2),
        "t_total_clustered": round(tstat(wk_sig_minus_base), 2),
    }
    out["timing"] = timing
    print(f"\n=== 4. Scomposizione: QUANDO contro QUALE titolo (rendimento a 21 barre, costi inclusi) ===")
    print(f"titolo qualsiasi, giorno qualsiasi        : {timing['baseline_any_day']:+}%")
    print(f"titolo qualsiasi, giorni di segnale       : {timing['control_on_signal_days']:+}%   → effetto QUANDO {timing['timing_edge']:+} (t a cluster {timing['t_timing_clustered']})")
    print(f"titolo del segnale, giorni di segnale     : {timing['signals']:+}%   → effetto QUALE {ctl['edge']:+} (t a cluster {ctl['t_edge_clustered']})")
    print(f"totale segnale contro base                : {timing['total_edge']:+} (t a cluster {timing['t_total_clustered']})")

    # ---------- 5. e comprando semplicemente SPY nei giorni di segnale? ----------
    spy = fetch_prices(["SPY"], START, min_len=600).get("SPY")
    if spy is not None:
        sd = spy.index.strftime("%Y-%m-%d").tolist()
        sp = [float(v) for v in spy.values]
        sidx = {x: i for i, x in enumerate(sd)}
        breadth = {}
        for _, d, *_ in signals:
            breadth[d] = breadth.get(d, 0) + 1
        i0 = sidx[next(x for x in sd if x >= FROM)]
        uncond = [p for p in (fixed_pnl(sp, i + 1, HORIZON) for i in range(i0, len(sp) - HORIZON - 2)) if p is not None]

        def spy_on(days):
            vals, wk = [], {}
            for d in days:
                if d in sidx:
                    p = fixed_pnl(sp, sidx[d] + 1, HORIZON)
                    if p is not None:
                        vals.append(p)
                        wk.setdefault(week_key(d), []).append(p)
            diffs = [np.mean(v) - np.mean(uncond) for v in wk.values()]
            return (round(float(np.mean(vals)), 2) if vals else None, len(vals),
                    round(tstat(diffs), 2) if len(diffs) > 1 else None)

        any_days = sorted(breadth)
        broad_days = sorted(d for d, k in breadth.items() if k >= 3)
        m_any, n_any, t_any = spy_on(any_days)
        m_broad, n_broad, t_broad = spy_on(broad_days)
        out["spy"] = {"unconditional": round(float(np.mean(uncond)), 2),
                      "on_signal_days": m_any, "n_signal_days": n_any, "t_signal_days": t_any,
                      "on_broad_days": m_broad, "n_broad_days": n_broad, "t_broad_days": t_broad}
        print(f"\n=== 5. SPY comprato il giorno dopo un segnale, tenuto 21 barre ===")
        print(f"SPY in un giorno qualsiasi                        : {out['spy']['unconditional']:+}%")
        print(f"SPY dopo giorni con almeno 1 segnale ({n_any} giorni)  : {m_any:+}%  (t a cluster {t_any})")
        print(f"SPY dopo giorni con almeno 3 segnali ({n_broad} giorni) : {m_broad:+}%  (t a cluster {t_broad})")

    print(f"\nsalvato: {save_output('scanner_persistence.json', out)}")


if __name__ == "__main__":
    main()
