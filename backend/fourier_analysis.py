
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

class FourierAnalyzer:
    def __init__(self, data):
        """
        Initialize the analyzer with price data.
        Expects data to be a pandas Series or single-column DataFrame.
        """
        if isinstance(data, pd.DataFrame):
            data = data.squeeze()
        self.px = pd.Series(data).dropna()
        self.px.index = pd.to_datetime(self.px.index)
        
        # Log-transformation for better stability
        self.lp = np.log(self.px).astype(float)
        self.vals = self.lp.to_numpy().ravel()
        self.N = len(self.vals)
        self.t = np.arange(self.N)
        
        # Calculate linear trend once
        self.coef = np.polyfit(self.t, self.vals, 1)
        self.trend = np.polyval(self.coef, self.t)
        self.resid = self.vals - self.trend
        
        # State for FFT results
        self.freqs = None
        self.fft_vals = None
        self.power = None
        self.top_idx = None
        self.top_freqs = None
        self.top_amps = None
        self.top_phase = None

    def compute_fft(self):
        """
        Perform Real FFT on the detrended residual.
        """
        self.freqs = np.fft.rfftfreq(self.N, d=1.0)
        self.fft_vals = np.fft.rfft(self.resid)
        self.power = np.abs(self.fft_vals)
        return self.freqs, self.power

    def get_top_k_components(self, k=8):
        """
        Extract the Top K dominant frequencies (excluding DC component).
        """
        if self.power is None:
            self.compute_fft()
            
        # Sort by power (amplitude), excluding index 0 (DC trend)
        # We index power[1:] so original index i becomes i+1
        order = np.argsort(self.power[1:])[::-1][:k] + 1
        self.top_idx = np.sort(order)
        
        self.top_freqs = self.freqs[self.top_idx]
        # Amplitude = 2/N * |FFT|
        self.top_amps = (2.0 / self.N) * np.abs(self.fft_vals[self.top_idx])
        self.top_phase = np.angle(self.fft_vals[self.top_idx])
        
        # Calculate periods (1/freq)
        periods = (1 / np.maximum(self.top_freqs, 1e-12)).astype(int)
        
        return pd.DataFrame({
            "freq": self.top_freqs,
            "period": periods,
            "amplitude": self.top_amps,
            "phase": self.top_phase
        })

    def low_pass_filter(self, cutoff_pct=0.03):
        """
        Reconstruct signal using a low-pass filter (keeping lowest % of frequencies).
        Returns reconstructed price series.
        """
        if self.fft_vals is None:
            self.compute_fft()
            
        n_cutoff = max(2, int(len(self.fft_vals) * cutoff_pct))
        
        keep = np.zeros_like(self.fft_vals, dtype=bool)
        keep[:n_cutoff] = True
        
        fft_filt = np.zeros_like(self.fft_vals, dtype=complex)
        fft_filt[keep] = self.fft_vals[keep]
        
        # Inverse FFT to get filtered log-residuals
        resid_recon = np.fft.irfft(fft_filt, n=self.N)
        
        # Add back trend
        lp_recon = self.trend + resid_recon
        
        # Exp to get back to price
        px_recon = np.exp(lp_recon)
        
        return pd.Series(px_recon, index=self.px.index)

    def synthesize_scenarios(self, n_scenarios=5, horizon=60, phase_jitter=0.8, amp_scale=1.0):
        """
        Generate synthetic future price scenarios based on Top K components.
        """
        if self.top_freqs is None:
            self.get_top_k_components(k=8)
            
        scenarios = []
        rng = np.random.default_rng()
        
        # Time array for past + horizon
        t_total = np.arange(self.N + horizon)
        trend_total = np.polyval(self.coef, t_total)
        
        for i in range(n_scenarios):
            # Jitter phases for variety, keep original phases as baseline
            current_phases = self.top_phase.copy()
            if phase_jitter > 0 and i > 0: # Scenario 0 can be "base case" or also jittered? 
                # Let's jitter all to explore variance, or keep first one deterministic? 
                # User code jittered based on seed.
                current_phases += rng.normal(0.0, phase_jitter, size=len(current_phases))
            
            resid_synth = np.zeros_like(t_total, dtype=float)
            
            # Sum of cosines
            for A, freq, ph in zip(self.top_amps * amp_scale, self.top_freqs, current_phases):
                w = 2 * np.pi * freq
                resid_synth += A * np.cos(w * t_total + ph)
                
            lp_synth = trend_total + resid_synth
            px_synth = np.exp(lp_synth)
            
            # Create index
            last_date = self.px.index[-1]
            # Try infer freq
            freq = pd.infer_freq(self.px.index)
            if freq is None: freq = 'D' # Default to daily if unknown
            
            future_dates = pd.date_range(last_date, periods=horizon + 1, freq=freq)[1:]
            full_index = self.px.index.append(future_dates)
            
            scenarios.append(pd.Series(px_synth, index=full_index))
            
        return scenarios

    def plot_dashboard(self, ticker="Asset", horizon=60):
        """
        Plot the 5 perspectives dashboard.
        """
        # Ensure calculations are done
        self.compute_fft()
        top_k_df = self.get_top_k_components()
        recon = self.low_pass_filter(cutoff_pct=0.03)
        scenarios = self.synthesize_scenarios(n_scenarios=5, horizon=horizon)
        
        fig = plt.figure(figsize=(15, 12), constrained_layout=True)
        axs = fig.subplot_mosaic([
            ['spectrum', 'components'],
            ['reconstruction', 'reconstruction'],
            ['scenarios', 'scenarios']
        ])
        
        # 1. FFT Spectrum
        mask = self.freqs > 0
        axs['spectrum'].plot(self.freqs[mask], self.power[mask], color='purple')
        axs['spectrum'].set_title(f"{ticker} - FFT Spectrum (Magnitude)")
        axs['spectrum'].set_xlabel("Frequency")
        axs['spectrum'].set_ylabel("Power")
        axs['spectrum'].grid(True, alpha=0.3)
        
        # 2. Components Table (Top K)
        # Creating a simple table visualization or bar chart
        # Let's do a bar chart of Amplitudes for the components
        axs['components'].bar(top_k_df['period'].astype(str), top_k_df['amplitude'], color='teal')
        axs['components'].set_title("Top 8 Dominant Cycles (Periods in bars)")
        axs['components'].set_xlabel("Period")
        axs['components'].set_ylabel("Amplitude (Log)")
        axs['components'].grid(True, axis='y', alpha=0.3)

        # 3. Reconstruction
        axs['reconstruction'].plot(self.px.index, self.px.values, label='Actual Price', alpha=0.6, color='black')
        axs['reconstruction'].plot(recon.index, recon.values, label='Low-Pass Filtered (Trend)', color='orange', linewidth=2)
        axs['reconstruction'].set_title("Price vs Low-Pass Reconstruction")
        axs['reconstruction'].legend()
        axs['reconstruction'].grid(True, alpha=0.3)
        
        # 4. Future Scenarios
        axs['scenarios'].plot(self.px.index, self.px.values, label='History', color='black', linewidth=1.5)
        
        # Plot future zone
        future_start = self.px.index[-1]
        future_end = scenarios[0].index[-1]
        axs['scenarios'].axvspan(future_start, future_end, color='orange', alpha=0.1, label='Forecast Horizon')
        
        for i, s in enumerate(scenarios):
            # Plot only the tail (history + future) to avoid clutter? Or full path?
            # User plot showed full path reconstruction. Let's do full path but dashed.
            axs['scenarios'].plot(s.index, s.values, linestyle='--', alpha=0.7, label=f'Scenario {i+1}')
            
        axs['scenarios'].set_title(f"5 Synthetic Future Scenarios (Fourier Projection + Jitter)")
        axs['scenarios'].legend(loc='upper left')
        axs['scenarios'].grid(True, alpha=0.3)
        
        return fig
