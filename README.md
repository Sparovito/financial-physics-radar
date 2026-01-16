# Financial Physics Market Radar

A powerful financial analysis tool that leverages principles of physics (Least Action Principle, Kinetic/Potential Energy) to visualize market dynamics and forecast price movements.

## Features

*   **Market Radar**: Dynamic visualization of market energy states (Overheating, Volatility, Equilibrium, Accumulation).
*   **Time Travel**: Explore historical market states with an interactive timeline and trails to see asset trajectories.
*   **Z-Score Analysis**: Normalize market data to compare distinct assets on a unified physics-based canvas.
*   **Fourier Forecasting**: Project future price movements using spectral analysis.

## Project Structure

*   `backend/`: Python FastAPI application handling data fetching and complex calculations.
*   `frontend/`: Static HTML/JS/CSS interface for visualization (served by the backend).

## Local Development

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Server**:
    ```bash
    uvicorn backend.main:app --reload
    ```
    Or use the Procfile command locally if you have `foreman` or similar tools.

4.  **Access the App**:
    Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Deployment (Railway)

This project is configured for deployment on [Railway](https://railway.app/).

1.  **Push to GitHub**: Ensure your code is in a GitHub repository.
2.  **New Project on Railway**: Connect your GitHub repo.
3.  **Configuration**:
    *   Railway will automatically detect the `Procfile` and `requirements.txt` in the root.
    *   The start command `web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT` is defined in `Procfile`.
    *   No manual environment variables are strictly required for the public API, but ensure the build process installs Python dependencies.

## Technologies

*   **Backend**: Python, FastAPI, Pandas, NumPy, YFinance, SciPy.
*   **Frontend**: HTML5, Vanilla JS, Plotly.js.
