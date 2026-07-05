"""
Test per kalman_llt_velocity (logic.py) — la "cinetica causale" vera.

Motivazione: nel modello local-level (1 stato) la cinetica causale degenera
nella sorpresa (kin = cost × pot, identità esatta). Per avere una VELOCITÀ
causale distinta serve il filtro di Kalman a trend locale (2 stati:
livello + velocità). È l'analogo causale del filtro HP: azione di ordine 2
(penalizza l'accelerazione), coerente con la fisica del progetto.

Proprietà verificate:
1. Su trend lineare pulito la velocità converge alla pendenza vera.
2. Causalità: il prefisso non cambia troncando la serie.
3. Scale-invariance della velocity_pct (px e 100·px danno lo stesso output).
4. Meno ritardo della catena attuale EMA20→diff→EMA14 a parità di rumorosità
   accettabile (cross-correlation con la derivata vera su sinusoide rumorosa).

Esecuzione: backend/venv/bin/python backend/tests/test_llt_velocity.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _series(vals, start="2023-01-02"):
    idx = pd.date_range(start, periods=len(vals), freq="B")
    return pd.Series(np.asarray(vals, dtype=float), index=idx)


def _v1_slope(px):
    """Catena attuale: EMA20 del prezzo -> diff -> EMA14 (per confronto lag)."""
    F = px.ewm(span=20, adjust=False).mean()
    return F.diff().fillna(0).ewm(span=14, adjust=False).mean()


def test_linear_trend_convergence(kalman_llt_velocity):
    # trend +0.5/giorno partendo da 100
    n = 400
    px = _series(100 + 0.5 * np.arange(n))
    out = kalman_llt_velocity(px, lam=1e-4)
    v = np.array(out["velocity"])
    # dopo la convergenza la velocità stimata deve essere ~0.5
    tail = v[200:]
    assert abs(tail.mean() - 0.5) < 0.01, f"velocità media {tail.mean():.4f} != 0.5"
    assert tail.std() < 0.01, f"velocità instabile su trend pulito (std {tail.std():.4f})"
    # velocity_pct ~ 0.5/level*100
    vp = np.array(out["velocity_pct"])[300:]
    lvl = np.array(out["level"])[300:]
    exp = 100 * 0.5 / lvl.mean()
    assert abs(vp.mean() - exp) < 0.02
    print(f"  OK convergenza trend lineare (v={tail.mean():.4f}, v_pct={vp.mean():.3f}%/g)")


def test_causality_prefix(kalman_llt_velocity):
    rng = np.random.default_rng(5)
    px = _series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 500))))
    full = kalman_llt_velocity(px, lam=1e-5)
    cut = 350
    part = kalman_llt_velocity(px.iloc[:cut], lam=1e-5)
    err = max(abs(a - b) for a, b in zip(part["velocity_pct"], full["velocity_pct"][:cut]))
    assert err < 1e-10, f"NON CAUSALE: prefisso cambia (max err {err:.2e})"
    print("  OK causalità (prefisso identico troncando)")


def test_scale_invariance(kalman_llt_velocity):
    rng = np.random.default_rng(7)
    base = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 400)))
    a = kalman_llt_velocity(_series(base), lam=1e-5)["velocity_pct"]
    b = kalman_llt_velocity(_series(base * 100), lam=1e-5)["velocity_pct"]
    err = max(abs(x - y) for x, y in zip(a, b))
    assert err < 1e-8, f"velocity_pct NON scale-invariant (max err {err:.2e})"
    print("  OK scale-invariance (px e 100·px identici)")


def test_lower_lag_than_v1_chain(kalman_llt_velocity):
    # sinusoide di periodo 120 barre + rumore: confrontiamo il lag ottimo
    # (cross-correlation con la derivata VERA) di v2 vs catena EMA attuale
    rng = np.random.default_rng(11)
    n = 720
    t = np.arange(n)
    period = 120.0
    clean = 100 + 8 * np.sin(2 * np.pi * t / period)
    noisy = clean * (1 + rng.normal(0, 0.004, n))
    px = _series(noisy)
    true_deriv = np.gradient(clean)

    def best_lag(sig):
        best_l, best_c = 0, -9
        s = np.asarray(sig)
        for L in range(0, 41):
            a = true_deriv[: n - L]
            b = s[L:]
            c = np.corrcoef(a[60:], b[60:])[0, 1]
            if c > best_c:
                best_c, best_l = c, L
        return best_l, best_c

    def flips(sig):
        s = np.sign(np.asarray(sig)[60:])
        return int(np.sum(np.abs(np.diff(s)) > 0))

    v1 = _v1_slope(px).values
    lag_v1, c_v1 = best_lag(v1)
    flips_v1 = flips(v1)

    # DOMINANZA a parità di rumorosità: con lam=3e-4 il LLT deve avere
    # MENO lag senza più cambi di segno (whipsaw) della catena EMA.
    out_eq = kalman_llt_velocity(px, lam=3e-4)
    lag_eq, c_eq = best_lag(out_eq["velocity"])
    assert flips(out_eq["velocity"]) <= flips_v1, "più whipsaw della catena EMA"
    assert lag_eq < lag_v1, f"LLT non domina: lag {lag_eq} >= v1 {lag_v1}"

    # Con lam=1e-3 il lag deve circa dimezzarsi mantenendo fedeltà alta.
    out_fast = kalman_llt_velocity(px, lam=1e-3)
    lag_fast, c_fast = best_lag(out_fast["velocity"])
    assert lag_fast <= lag_v1 - 5, f"riduzione lag insufficiente: {lag_fast} vs {lag_v1}"
    assert c_fast > 0.99, f"correlazione degradata: {c_fast:.3f}"

    print(f"  OK lag: v1 EMA-chain = {lag_v1}g/{flips_v1} flips | "
          f"LLT λ=3e-4 = {lag_eq}g (pari flips) | LLT λ=1e-3 = {lag_fast}g (corr {c_fast:.3f})")


def main():
    from logic import kalman_llt_velocity  # RED: non esiste ancora

    test_linear_trend_convergence(kalman_llt_velocity)
    test_causality_prefix(kalman_llt_velocity)
    test_scale_invariance(kalman_llt_velocity)
    test_lower_lag_than_v1_chain(kalman_llt_velocity)
    print("OK test_llt_velocity — 4/4")


if __name__ == "__main__":
    main()
