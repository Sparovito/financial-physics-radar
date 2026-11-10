"""
Confronto OUT-OF-SAMPLE: STABLE v1 (trend) vs v2 (Kalman LLT) vs ARANCIONE
vs COMBO. Parametri scelti SOLO sul train (primo 70% del calendario),
giudizio SOLO sull'OOS. Costi 0.05%/lato, esecuzione t+1.

    backend/venv/bin/python backend/research/oos_comparison.py
"""
from common import (np, sample_universe, fetch_prices, orange_inputs, save_output, tstat, COST)
from logic import kalman_llt_velocity
from stable_strategy import (backtest_stable, backtest_potential_discharge, backtest_combo)

START = "2023-01-01"


def agg(rows):
    a = {k: np.array([r[k] for r in rows], dtype=float) for k in rows[0]}
    alpha = a["roi"] - a["expo"] / 100 * a["bh"]
    return {"mean_roi": round(float(a["roi"].mean()), 1),
            "mean_sharpe": round(float(np.nanmean(a["sharpe"])), 2),
            "mean_dd": round(float(a["dd"].mean()), 1),
            "mean_expo": round(float(a["expo"].mean()), 1),
            "alpha": round(float(alpha.mean()), 1), "t_alpha": round(tstat(alpha), 2),
            "pct_beat_bh": round(float((a["roi"] > a["bh"]).mean() * 100), 1)}


def main():
    sample, _ = sample_universe()
    prices = fetch_prices(sample, START, min_len=400)
    all_dates = sorted({d for px in prices.values() for d in px.index.strftime("%Y-%m-%d")})
    si = int(len(all_dates) * 0.7)
    split, train_end = all_dates[si], all_dates[si - 1]
    print(f"{len(prices)} ticker | train fino a {train_end} | OOS da {split} a {all_dates[-1]}")

    sig = {}
    for t, px in prices.items():
        dates, pr, pot, F = orange_inputs(px)
        v1 = px.ewm(span=20, adjust=False).mean().diff().fillna(0).ewm(span=14, adjust=False).mean().values.tolist()
        v2 = {lam: kalman_llt_velocity(px, lam=lam)["velocity_pct"] for lam in (3e-4, 1e-3, 3e-3)}
        sig[t] = {"dates": dates, "prices": pr, "pot": pot, "F": F, "v1": v1, "v2": v2}

    def run(fn):
        tr, oo = [], []
        for s in sig.values():
            for rows, kw in ((tr, {"end_date": train_end}), (oo, {"start_date": split})):
                st = fn(s, kw)["stats"]
                rows.append({"roi": st["total_return"], "sharpe": st["sharpe"],
                             "dd": st["max_drawdown"], "expo": st["exposure_pct"],
                             "bh": st["buy_hold_return"]})
        return agg(tr), agg(oo)

    common = dict(execution_lag=1, cost_pct=COST)
    results = {"split": {"train_end": train_end, "oos_start": split, "oos_end": all_dates[-1]}}

    tr, oo = run(lambda s, kw: backtest_stable(s["dates"], s["prices"], s["v1"], mode="LONG", **common, **kw))
    results["v1_stable"] = {"params": "EMA 0/0", "train": tr, "oos": oo}

    def best_of(name, grid, fn):
        best, all_cfg = None, {}
        for key, p in grid:
            tr, oo = run(lambda s, kw: fn(s, kw, p))
            all_cfg[key] = {"train": tr, "oos": oo}
            if best is None or tr["mean_sharpe"] > best[1]["mean_sharpe"]:
                best = (key, tr, oo)
        results[name] = {"params": best[0], "train": best[1], "oos": best[2], "grid": all_cfg}

    best_of("v2_llt",
            [(f"lam={lam:.0e},th={e}", (lam, e)) for lam in (3e-4, 1e-3, 3e-3) for e in (0.0, 0.02, 0.05)],
            lambda s, kw, p: backtest_stable(s["dates"], s["prices"], s["v2"][p[0]], mode="LONG",
                                             entry_th=p[1], exit_th=-p[1], **common, **kw))
    grid_d = [(f"z>{z},hold={h}", (z, h)) for z in (1.5, 2.0, 2.5) for h in (10, 21, 42)]
    best_of("arancione", grid_d,
            lambda s, kw, p: backtest_potential_discharge(s["dates"], s["prices"], s["pot"], s["F"],
                                                          entry_z=p[0], horizon=p[1], **common, **kw))
    best_of("combo", grid_d,
            lambda s, kw, p: backtest_combo(s["dates"], s["prices"], s["v1"], s["pot"], s["F"],
                                            entry_z=p[0], horizon=p[1], **common, **kw))

    path = save_output("oos_comparison.json", results)
    print(f"\n{'strategia':12s} {'config (scelta su train)':26s} | OOS: ROI  Sharpe   DD   expo  alpha(t)")
    for name in ("v1_stable", "v2_llt", "arancione", "combo"):
        r = results[name]; o = r["oos"]
        print(f"{name:12s} {r['params']:26s} | {o['mean_roi']:8.1f} {o['mean_sharpe']:6.2f} {o['mean_dd']:5.1f} "
              f"{o['mean_expo']:5.1f} {o['alpha']:6.1f}({o['t_alpha']})")
    for name in ("arancione", "combo"):
        alphas = [v["oos"]["alpha"] for v in results[name]["grid"].values()]
        sharpes = [v["oos"]["mean_sharpe"] for v in results[name]["grid"].values()]
        print(f"robustezza {name}: alpha OOS su tutta la griglia [{min(alphas)}, {max(alphas)}], "
              f"Sharpe [{min(sharpes)}, {max(sharpes)}]")
    print(f"\nsalvato: {path}")


if __name__ == "__main__":
    main()
