import numpy as np
import pandas as pd
import yfinance as yf
from scipy.signal import savgol_filter

# --- 1. Gestione Dati ---
class MarketData:
    """
    Gestisce il download e la pre-elaborazione dei dati finanziari.
    Include un fallback a dati sintetici (Mock) se il download fallisce.
    """
    def __init__(self, ticker, start_date=None, end_date=None):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.data = None

    def fetch(self):
        """
        Scarica i dati da Yahoo Finance.
        Se fallisce (per SSL o altro), genera dati sintetici realistici.
        """
        print(f"Recupero dati per {self.ticker}...")
        
        # 1. TENTATIVO DI DOWNLOAD REALE
        try:
            # Force SSL bypass context locally
            import ssl
            try:
                _create_unverified_https_context = ssl._create_unverified_context
            except AttributeError:
                pass
            else:
                ssl._create_default_https_context = _create_unverified_https_context

            self.ticker_obj = yf.Ticker(self.ticker)
            
            if self.start_date:
                self.data = self.ticker_obj.history(start=self.start_date, end=self.end_date)
            else:
                self.data = self.ticker_obj.history(period="2y")
                
            if self.data.empty:
                 print("Dati vuoti, tento periodo max...")
                 self.data = self.ticker_obj.history(period="1y")

            # Post-processing se abbiamo dati
            if not self.data.empty:
                return self._clean_data()
            else:
                print("❌ Download YFinance vuoto. Passo ai dati Mock.")
                
        except Exception as e:
            print(f"⚠️ Errore download yfinance: {e}")
            raise ValueError(f"Impossibile scaricare dati reali per {self.ticker}. Errore: {e}")

        # 2. FALLBACK RIMOSSO (Su richiesta utente)
        return self._clean_data()

    def _clean_data(self):
        # Pulisce i dati reali
        if isinstance(self.data.columns, pd.MultiIndex):
             self.data.columns = self.data.columns.get_level_values(0)
             
        # Normalize columns (Capitalize)
        self.data.columns = [c.capitalize() for c in self.data.columns]
        
        if self.data.index.tz is not None:
             self.data.index = self.data.index.tz_localize(None)

        self.data = self.data.dropna()
        
        # [NEW] Save FULL DataFrame for advanced indicators logic
        self.df_full = self.data.copy()

        if 'Close' in self.data.columns:
             self.data = self.data['Close']
        else:
             self.data = self.data.iloc[:, 0]
             
        self.data.name = self.ticker
        print(f"Caricati {len(self.data)} punti dati reali.")
        return self.data

    def _generate_mock_data(self):
        """
        Genera una serie temporale realistica che assomiglia all'S&P 500.
        """
        print(f"🔵 Generazione dati simulati per {self.ticker}...")
        
        # Parametri simulazione
        days = 500
        start_price = 400.0
        
        # Genera date
        dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='B')
        
        # Genera prezzi (Random Walk con trend)
        np.random.seed(42) # Seme fisso per coerenza
        returns = np.random.normal(loc=0.0005, scale=0.01, size=days) # Drift positivo leggero
        price_path = start_price * (1 + returns).cumprod()
        
        # Aggiungi un po' di "ciclicità" finta per Fourier
        t = np.arange(days)
        cycle = 10 * np.sin(2 * np.pi * t / 50) # Ciclo di 50 giorni
        price_path += cycle
        
        self.data = pd.Series(price_path, index=dates, name=self.ticker)
        print(f"Generati {len(self.data)} punti dati sintetici.")
        return self.data

# --- 2. Motore Fourier ---
class FourierEngine:
    """
    Esegue l'Analisi Spettrale e la Generazione di Futuri Sintetici.
    """
    def __init__(self, price_series, top_k=8):
        # Restriction: Use only the last 252 trading days (1 year) for Fourier Analysis
        # This focuses the cycle detection on the current market regime.
        WINDOW_SIZE = 252
        if len(price_series) > WINDOW_SIZE:
            self.px = price_series[-WINDOW_SIZE:]
            # print(f"🔹 Fourier Engine: analyzing last {WINDOW_SIZE} days only.")
        else:
            self.px = price_series
            
        self.top_k = int(top_k)
        self._fit()

    def _fit(self):
        # 1. Trasformazione logaritmica
        self.lp = np.log(self.px.astype(float))
        self.t = np.arange(len(self.lp))
        self.N = len(self.lp)
        
        # 2. Estrazione Trend Lineare
        self.coef = np.polyfit(self.t, self.lp.values, 1)
        self.trend = np.polyval(self.coef, self.t)
        self.resid = self.lp.values - self.trend
        
        # 3. FFT
        self.freqs = np.fft.rfftfreq(self.N, d=1.0)
        self.F = np.fft.rfft(self.resid)
        power = np.abs(self.F)
        
        # 4. Filtra le migliori TOP_K frequenze
        # (ignora la componente DC all'indice 0)
        if len(power) > 1:
            order = np.argsort(power[1:])[::-1][:self.top_k] + 1
            self.top_idx = np.sort(order)
            self.top_freqs = self.freqs[self.top_idx]
            self.top_amps = (2.0 / self.N) * np.abs(self.F[self.top_idx])
            self.top_phase = np.angle(self.F[self.top_idx])
        else:
            # Fallback per serie troppo corte
            self.top_idx = []
            self.top_freqs = []
            self.top_amps = []
            self.top_phase = []

    def reconstruct_scenario(self, future_horizon=60, amp_scale=1.0, phase_jitter=0.0):
        # Vettore tempo: Passato + Futuro
        t2 = np.arange(self.N + future_horizon)
        
        # Estendi Trend Lineare
        trend2 = np.polyval(self.coef, t2)
        
        # Ricostruisci oscillazione
        phases = self.top_phase.copy()
        if phase_jitter > 0:
            rng = np.random.default_rng()
            phases += rng.normal(0.0, phase_jitter, size=len(phases))
            
        resid2 = np.zeros_like(t2, dtype=float)
        for A, w, ph in zip(self.top_amps * amp_scale, 2 * np.pi * self.top_freqs, phases):
            resid2 += A * np.cos(w * t2 + ph)
            
        lp2 = trend2 + resid2
        px2 = np.exp(lp2)
        
        # Genera Indice Temporale corretto
        try:
            last_date = self.px.index[-1]
            # Inferisci frequenza o default a Business Day 'B'
            freq = pd.infer_freq(self.px.index)
            if not freq: freq = 'B'
            
            future_dates = pd.date_range(last_date, periods=future_horizon + 1, freq=freq)[1:]
            
            # Combina index passato + futuro
            # Nota: px.index potrebbe avere timezone, future_dates no. 
            # Per semplicità, convertiamo tutto in stringa ISO o naive timestamp nel main.
            # Qui ritorniamo solo i valori o una Series con indice best-effort.
            full_idx = self.px.index.tolist() + future_dates.tolist()
        except:
            full_idx = range(len(px2))
            
        return full_idx, px2

    def get_components(self):
        if len(self.top_freqs) == 0:
            return []
            
        period_bars = (1 / np.maximum(self.top_freqs, 1e-12)).astype(int)
        
        # Restituiamo una lista di dizionari (serializzabile JSON)
        comps = []
        for i in range(len(self.top_freqs)):
            comps.append({
                "frequency": float(self.top_freqs[i]),
                "period": int(period_bars[i]),
                "amplitude": float(self.top_amps[i]),
                "phase": float(self.top_phase[i])
            })
        
        # Ordina per ampiezza decrescente
        comps.sort(key=lambda x: x["amplitude"], reverse=True)
        return comps

# --- 3. Motore Minima Azione ---
class ActionPath:
    """
    Calcola la traiettoria di 'Minima Azione'.
    """
    def __init__(self, price_series, alpha=1.0, beta=1.0, lookback_span=20):
        self.px = price_series
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.span = int(lookback_span)
        self._compute()

    def _compute(self):
        # 1. Campo Fondamentale F (EWMA)
        self.F = self.px.ewm(span=self.span, adjust=False).mean()
        F_vals = self.F.values.astype(float)
        n = len(F_vals)
        
        if n < 3:
            raise ValueError("Serie temporale troppo corta.")

        # 2. Sistema Tridiagonale
        A, B = self.alpha, self.beta
        
        lower = np.full(n-1, -A, dtype=float)
        diag  = np.full(n,   B + 2*A, dtype=float)
        diag[0] = B + A
        diag[-1] = B + A
        upper = np.full(n-1, -A, dtype=float)
        rhs   = B * F_vals

        # 3. Risolvi
        self.x_star_vals = self._solve_tridiag(lower, diag, upper, rhs)
        self.px_star = pd.Series(self.x_star_vals, index=self.px.index)

        # 4. Calcola Densità
        self.dX = self.px_star.diff().fillna(0.0)
        self.kin_density = 0.5 * A * (self.dX**2)
        self.pot_density = 0.5 * B * ((self.px_star - self.F)**2)
        
        self.action_density = self.kin_density + self.pot_density
        self.cumulative_action = self.action_density.cumsum()
        
        # 5. Indicatori Aggiuntivi (Slope & Z-Residuo)
        # Slope è dX (velocità del percorso x*)
        
        # Z-Residuo: Z-score della divergenza tra Prezzo Reale e Fondamentale
        self.divergence = self.px - self.F
        win = 20 # Finestra mobile per Z-Score locale
        roll_mean = self.divergence.rolling(window=win).mean()
        roll_std = self.divergence.rolling(window=win).std()
        
        self.z_residuo = (self.divergence - roll_mean) / roll_std
        # Sanitizzazione robusta per JSON (Inf -> 0, NaN -> 0)
        self.z_residuo = self.z_residuo.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        # SMOTTHING SU RICHIESTA UTENTE (Riduce "vibrazioni")
        self.z_residuo = self.z_residuo.ewm(span=10).mean()

    def _solve_tridiag(self, a, b, c, d):
        n = len(b)
        c_ = np.zeros(n-1, dtype=float)
        d_ = np.zeros(n, dtype=float)
        b_ = b.astype(float).copy()
        
        c_[0] = c[0] / b_[0]
        d_[0] = d[0] / b_[0]
        for i in range(1, n-1):
            denom = b_[i] - a[i-1]*c_[i-1]
            c_[i] = c[i] / denom
            d_[i] = (d[i] - a[i-1]*d_[i-1]) / denom
            
        d_[n-1] = (d[n-1] - a[n-2]*d_[n-2]) / (b_[n-1] - a[n-2]*c_[n-2])
        
        x = np.zeros(n, dtype=float)
        x[-1] = d_[n-1]
        x = np.zeros(n, dtype=float)
        x[-1] = d_[n-1]
        for i in range(n-2, -1, -1):
            x[i] = d_[i] - c_[i]*x[i+1]
        return x

# --- 4. Market Scanner (Radar) ---
class MarketScanner:
    """
    Analizza una lista di titoli in parallelo e calcola lo Z-Score
    Dell'Energia Cinetica e Potenziale corrente.
    """
    def __init__(self, tickers_list):
        self.tickers = tickers_list
        
    def scan(self):
        import concurrent.futures
        
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:  # Limited to 5 to avoid rate limits
            future_to_ticker = {executor.submit(self._analyze_single, t): t for t in self.tickers}
            
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    data = future.result()
                    if data:
                        results.append(data)
                except Exception as exc:
                    print(f'{ticker} generated an exception: {exc}')
                    
        return results

    def _analyze_single(self, ticker):
        try:
            # Scarica 1 anno di dati (sufficiente per statistica Z-Score)
            md = MarketData(ticker)
            px = md.fetch()
            
            if len(px) < 100: return None
            
            # Calcola Meccanica (Alpha standard 200, Beta 1.0)
            mech = ActionPath(px, alpha=200, beta=1.0)
            
            # === ROLLING Z-SCORE TO ELIMINATE LOOK-AHEAD BIAS ===
            # Use 252-day (1 year) rolling window - each point only uses PAST data
            ZSCORE_WINDOW = 252
            
            # 1. Energia Cinetica (Momentum) - ROLLING Z-Score
            kin = mech.kin_density
            roll_kin_mean = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
            roll_kin_std = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
            z_kin_series = (kin - roll_kin_mean) / (roll_kin_std + 1e-6)
            z_kin_series = z_kin_series.fillna(0)
            
            # 2. Energia Potenziale (Tensione) - ROLLING Z-Score
            pot = mech.pot_density
            roll_pot_mean = pot.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
            roll_pot_std = pot.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
            z_pot_series = (pot - roll_pot_mean) / (roll_pot_std + 1e-6)
            z_pot_series = z_pot_series.fillna(0)
            
            # Prendi ultimi 756 giorni (3 Anni Trading) per "Deep Time Travel" fino 2023
            HISTORY_LEN = 756
            
            # Preparazione vettori allineati (Padding a sinistra con None se < 252)
            def pad_left(lst, length, fill=None):
                return [fill] * (length - len(lst)) + lst
            
            # Calcola Z-Score dello Slope (dX) - ROLLING Z-Score
            slope = mech.dX
            roll_slope_mean = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
            roll_slope_std = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
            z_slope_series = (slope - roll_slope_mean) / (roll_slope_std + 1e-6)
            z_slope_series = z_slope_series.fillna(0)
            
            # Prendi al massimo HISTORY_LEN finali
            segment_px = px.iloc[-HISTORY_LEN:]
            segment_z_kin = z_kin_series.iloc[-HISTORY_LEN:]
            segment_z_pot = z_pot_series.iloc[-HISTORY_LEN:]
            segment_z_slope = z_slope_series.iloc[-HISTORY_LEN:]
            
            # Converti in lista e padding
            hist_dates = pad_left(segment_px.index.strftime('%Y-%m-%d').tolist(), HISTORY_LEN, None)
            hist_z_kin = pad_left(segment_z_kin.tolist(), HISTORY_LEN, None)
            hist_z_pot = pad_left(segment_z_pot.tolist(), HISTORY_LEN, None)
            hist_z_slope = pad_left(segment_z_slope.tolist(), HISTORY_LEN, None)
            hist_price = pad_left(segment_px.tolist(), HISTORY_LEN, None)

            # Snapshot Attuale (Ultimo valore valido)
            price = px.iloc[-1]
            change = (px.iloc[-1] - px.iloc[-2]) / px.iloc[-2] * 100

            # [NEW: User Request] Market Quality Metrics
            # 1. Average Kinetic Strength (Volatility/Energy)
            avg_abs_kin = z_kin_series.abs().mean()
            
            # 2. Market Cap (Size)
            try:
                # Note: This might slow down scanning slightly due to extra request
                info = md.ticker_obj.info
                market_cap = info.get('marketCap', 0)
            except:
                market_cap = 0
            
            # [ACCURATE] Calculate TRUE Point-in-Time Frozen Potential (like Main Chart)
            # This is slower but gives the EXACT same values as the Orange Line
            MIN_POINTS = 100
            SAMPLE_EVERY = 1  # Every day for accuracy
            
            frozen_pot_raw = []
            frozen_dates_raw = []
            
            # Build point-in-time series (no look-ahead bias)
            n_total = len(px)
            for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
                px_t = px.iloc[:t+1]
                try:
                    mech_t = ActionPath(px_t, alpha=200, beta=1.0)
                    frozen_pot_raw.append(float(mech_t.pot_density.iloc[-1]))
                    frozen_dates_raw.append(px.index[t].strftime('%Y-%m-%d'))
                except:
                    continue
            
            # Align with full price history (pad with 0 at start)
            padding_size = len(hist_price) - len(frozen_pot_raw)
            aligned_frozen_pot = [0] * padding_size + frozen_pot_raw
            aligned_frozen_dates = [None] * padding_size + frozen_dates_raw
            
            # Calculate Rolling Z-Score on aligned frozen potential
            frozen_pot_series = pd.Series(aligned_frozen_pot).fillna(0)
            roll_fpot_mean = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
            roll_fpot_std = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
            z_frozen_pot = ((frozen_pot_series - roll_fpot_mean) / (roll_fpot_std + 1e-6)).fillna(0).tolist()
            
            # [NEW] Calculate Frozen Strategy P/L using TRUE frozen Z-score
            strat_res = backtest_strategy(
                 prices=hist_price,
                 z_kinetic=z_frozen_pot,  # TRUE Frozen Z-Score (point-in-time)
                 z_slope=hist_z_slope,
                 dates=hist_dates
            )
            # Use TRADE P/L CURVE (resets to 0 between trades) to match Orange Line
            frozen_pnl_curve = strat_res['trade_pnl_curve'] 

            # === [NEW] FROZEN SUM STRATEGY ===
            # 1. Calculate Frozen Kinetic (point-in-time, shifted T-25)
            frozen_kin_raw = []
            for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
                px_t = px.iloc[:t+1]
                try:
                    mech_t = ActionPath(px_t, alpha=200, beta=1.0)
                    if len(mech_t.kin_density) >= 25:
                        frozen_kin_raw.append(float(mech_t.kin_density.iloc[-25]))
                    else:
                        frozen_kin_raw.append(0.0)
                except:
                    frozen_kin_raw.append(0.0)
            
            # 2. Calculate SUM (Kinetic + Potential)
            frozen_sum_raw = [k + p for k, p in zip(frozen_kin_raw, frozen_pot_raw)]
            
            # 3. Normalize SUM with Z-Score
            aligned_frozen_sum = [0] * padding_size + frozen_sum_raw
            frozen_sum_series = pd.Series(aligned_frozen_sum).fillna(0)
            roll_fsum_mean = frozen_sum_series.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
            roll_fsum_std = frozen_sum_series.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
            z_frozen_sum = ((frozen_sum_series - roll_fsum_mean) / (roll_fsum_std + 1e-6)).fillna(0).tolist()
            
            # 4. Apply Zero-Phase Low-Pass Filter (Butterworth) - requires scipy
            try:
                from scipy.signal import butter, filtfilt
                b, a = butter(N=2, Wn=0.05, btype='low')
                z_frozen_sum_filtered = filtfilt(b, a, z_frozen_sum).tolist()
                z_frozen_sum = z_frozen_sum_filtered
            except:
                pass  # Keep unfiltered if scipy fails
            
            # 5. Run SUM Strategy Backtest (threshold=-0.3)
            # Use -999 padding to prevent false signals
            z_sum_for_backtest = [-999] * padding_size + z_frozen_sum[padding_size:]
            
            strat_sum_res = backtest_strategy(
                 prices=hist_price,
                 z_kinetic=z_sum_for_backtest,
                 z_slope=hist_z_slope,
                 dates=hist_dates,
                 threshold=-0.3
            )
            sum_pnl_curve = strat_sum_res['trade_pnl_curve'] 

            return {
                "ticker": ticker,
                "avg_abs_kin": round(float(avg_abs_kin), 2),
                "market_cap": market_cap,
                # Valori attuali (per default view - usa ultimi valori validi)
                "z_kinetic": round(float(z_kin_series.iloc[-1]), 2),
                "z_potential": round(float(z_pot_series.iloc[-1]), 2),
                "price": round(float(price), 2),
                "change_pct": round(float(change), 2),
                # Storia Allineata (Tutti len=252)
                "history": {
                    "dates": hist_dates,
                    "z_kin": [round(x, 2) if x is not None else None for x in hist_z_kin],
                    "z_pot": [round(x, 2) if x is not None else None for x in hist_z_pot],
                    "z_slope": [round(x, 2) if x is not None else None for x in hist_z_slope],
                    "prices": [round(x, 2) if x is not None else None for x in hist_price],
                    "z_kin_frozen": [round(x, 2) if x is not None else None for x in hist_z_pot], # Legacy name mapping
                    "strategy_pnl": frozen_pnl_curve, # The "Orange Line" content (Cumulative)
                    "sum_pnl": sum_pnl_curve  # The "SUM Red Line" (Threshold=-0.3)
                }
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error analyzing {ticker}: {e}")
            print(traceback.format_exc())
            return None

# --- 5. Backtesting Strategy ---
def backtest_strategy(prices: list, z_kinetic: list, z_slope: list, dates: list, initial_capital=1000.0, start_date=None, end_date=None, threshold=0.0):
    """
    Esegue il backtest della strategia basata su Z-Scores.
    Filtra le operazioni in base a start_date e end_date.
    threshold: soglia per entry/exit (default 0).
    """
    capital = initial_capital
    in_position = False
    entry_price = None
    entry_date = None
    position_direction = None # 'LONG' or 'SHORT'
    
    trades = []
    trade_pnl_curve = [] # Individual trade P/L (0 = not invested)
    equity_curve = [] # Cumulative Strategy P/L % (Equity Curve)
    
    # Iterate through history
    for i, date in enumerate(dates):
        # --- HANDLE PADDING/NONE DATES ---
        if date is None:
            trade_pnl_curve.append(0)
            equity_curve.append(0)
            continue

        # --- DATE FILTERING ---
        if start_date and date < start_date:
            trade_pnl_curve.append(0)
            equity_curve.append(0)
            continue
            
        if end_date and date > end_date:
            trade_pnl_curve.append(0)
            # Use last valid equity or 0? 0 implies "not in stats range".
            # Consistency with other skips:
            equity_curve.append(0) 
            continue
            
        price = prices[i]
        z_kin = z_kinetic[i]
        z_sl = z_slope[i]
        
        # Skip if data is missing
        if price is None or z_kin is None or z_sl is None:
            trade_pnl_curve.append(0)
            # Equity curve: keep last value or 0 if start?
            last_eq = equity_curve[-1] if equity_curve else 0
            equity_curve.append(last_eq)
            continue
            
        if not in_position:
            # Check for entry signal
            if z_kin > threshold:
                in_position = True
                entry_price = price
                entry_date = date
                # Direction based on Z-ROC (Rate of Change of Z-Score) - 100% causal
                z_prev = z_kinetic[i-1] if i > 0 and z_kinetic[i-1] is not None else 0
                z_roc = z_kin - z_prev
                position_direction = 'LONG' if z_roc >= 0 else 'SHORT'
                trade_pnl_curve.append(0)
            else:
                trade_pnl_curve.append(0)
            
            # Current Equity = Capital (Cash)
            current_equity_pct = ((capital - initial_capital) / initial_capital) * 100
            equity_curve.append(round(current_equity_pct, 2))

        else:
            # Calculate current open P/L
            if position_direction == 'LONG':
                current_pnl = ((price - entry_price) / entry_price) * 100
            else:  # SHORT
                current_pnl = ((entry_price - price) / entry_price) * 100
            
            # Check for exit signal
            if z_kin < threshold:
                # Close the trade
                pnl_pct = current_pnl
                capital = capital * (1 + pnl_pct / 100)
                
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": date,
                    "direction": position_direction,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "capital_after": round(capital, 2)
                })
                
                in_position = False
                position_direction = None
                entry_price = None
                entry_date = None
                trade_pnl_curve.append(0) 
            else:
                # Still in position, show current P/L
                trade_pnl_curve.append(round(current_pnl, 2))
            
            # Current Equity = Capital (implied)
            # If closed just now, capital is updated. If open, projected capital.
            if in_position:
                temp_capital = capital * (1 + current_pnl / 100)
                current_equity_pct = ((temp_capital - initial_capital) / initial_capital) * 100
            else:
                current_equity_pct = ((capital - initial_capital) / initial_capital) * 100
            
            equity_curve.append(round(current_equity_pct, 2))
    
    # Check for OPEN Position at the end
    if in_position:
        # Calculate final Unrealized P/L
        final_price = prices[-1]
        
        if position_direction == 'LONG':
            unrealized_pnl = ((final_price - entry_price) / entry_price) * 100
        else:
            unrealized_pnl = ((entry_price - final_price) / entry_price) * 100
            
        trades.append({
            "entry_date": entry_date,
            "exit_date": "OPEN", 
            "direction": position_direction,
            "entry_price": round(entry_price, 2),
            "exit_price": round(final_price, 2),
            "pnl_pct": round(unrealized_pnl, 2),
            "capital_after": round(capital, 2)
        })
    
    # Calculate stats
    if len(trades) > 0:
        wins = sum(1 for t in trades if t['pnl_pct'] > 0)
        win_rate = (wins / len(trades)) * 100
        total_return = ((capital - initial_capital) / initial_capital) * 100
        avg_trade = sum(t['pnl_pct'] for t in trades) / len(trades)
    else:
        win_rate = 0
        total_return = 0
        avg_trade = 0

    backtest_stats = {
        "final_capital": round(capital, 2),
        "total_return": round(total_return, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": len(trades),
        "avg_trade_pct": round(avg_trade, 2)
    }
    
    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "trade_pnl_curve": trade_pnl_curve,
        "stats": backtest_stats
    }

