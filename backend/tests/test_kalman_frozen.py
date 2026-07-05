"""
Test di parità: kalman_frozen_series (O(n)) deve riprodurre ESATTAMENTE
i valori del ricalcolo brute-force point-in-time (O(n^2)) usato finora:

    for t in range(MIN_POINTS, n):
        mech_t = ActionPath(px[:t+1], alpha, beta)
        pot[-1], kin[-1], kin[-25], px_star[-1]

Fondamento: il percorso di minima azione è lo smoother MAP di un modello
state-space local-level (q=1/alpha, r=1/beta, init diffusa). L'ultimo punto
dello smoother su [0..t] = filtro di Kalman al tempo t; i punti interni
= fixed-lag smoother (RTS all'indietro).

Esecuzione: backend/venv/bin/python backend/tests/test_kalman_frozen.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _synthetic_px(n=400, seed=11):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.013, n)
    px = 120.0 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2023-02-01", periods=n, freq="B")
    return pd.Series(px, index=idx, name="TEST")


def _brute_force(px, alpha, beta, min_points=100, kin_lag=25):
    from logic import ActionPath
    pot_last, kin_last, kin_lagged, ma_price = [], [], [], []
    for t in range(min_points, len(px)):
        mech = ActionPath(px.iloc[:t + 1], alpha=alpha, beta=beta)
        pot_last.append(float(mech.pot_density.iloc[-1]))
        kin_last.append(float(mech.kin_density.iloc[-1]))
        if len(mech.kin_density) >= kin_lag:
            kin_lagged.append(float(mech.kin_density.iloc[-kin_lag]))
        else:
            kin_lagged.append(0.0)
        ma_price.append(float(mech.px_star.iloc[-1]))
    return (np.array(pot_last), np.array(kin_last),
            np.array(kin_lagged), np.array(ma_price))


def _check(name, brute, kalman, rtol=1e-6, atol=1e-8):
    """Confronto atol+rtol (semantica np.allclose).

    Nota: pot/kin sono QUADRATI di quantità vicine a zero — un rumore
    floating-point di ~1e-9 assoluto su x (inevitabile tra due algoritmi
    diversi ma matematicamente equivalenti) viene amplificato in errore
    relativo sul quadrato. La pipeline a valle arrotonda comunque a 2
    decimali, quindi atol=1e-8 è 6 ordini di grandezza sotto la soglia
    di rilevanza.
    """
    brute = np.asarray(brute, dtype=float)
    kalman = np.asarray(kalman, dtype=float)
    assert len(brute) == len(kalman), f"{name}: lunghezze diverse {len(brute)} vs {len(kalman)}"
    ok = np.allclose(brute, kalman, rtol=rtol, atol=atol)
    max_abs = float(np.max(np.abs(brute - kalman)))
    assert ok, f"{name}: parità violata (max diff assoluta {max_abs:.3e})"
    return max_abs


def main():
    from logic import kalman_frozen_series  # RED: non esiste ancora

    for alpha, beta, seed in [(200.0, 1.0, 11), (350.0, 1.0, 5), (200.0, 2.5, 23)]:
        px = _synthetic_px(seed=seed)
        b_pot, b_kin, b_kin_lag, b_ma = _brute_force(px, alpha, beta)

        res = kalman_frozen_series(px, alpha=alpha, beta=beta,
                                   min_points=100, kin_lag=25)

        assert list(res["t_index"]) == list(range(100, len(px))), "t_index errato"
        e1 = _check("pot_last", b_pot, res["pot_last"])
        e2 = _check("kin_last", b_kin, res["kin_last"])
        e3 = _check("kin_lag", b_kin_lag, res["kin_lag"])
        e4 = _check("ma_price", b_ma, res["ma_price"])
        print(f"OK α={alpha} β={beta}: pot {e1:.1e} | kin {e2:.1e} | "
              f"kin_lag25 {e3:.1e} | ma_price {e4:.1e}")

    print("OK test_kalman_frozen — parità O(n) vs brute-force O(n²) su 3 configurazioni")


if __name__ == "__main__":
    main()
