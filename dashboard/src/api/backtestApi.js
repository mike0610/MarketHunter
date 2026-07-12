import axios from "axios";

const api = axios.create({
    baseURL: (
        import.meta.env.VITE_API_BASE_URL
        || "http://127.0.0.1:8000"
    ),
});

/**
 * Triggers the backend backtest stub (api/backtest_api.py). Today this
 * only returns a hardcoded acknowledgement - it does not run a real
 * backtest yet (no engine wiring, no results storage/listing endpoint).
 * Kept here so the button on Backtests.jsx has somewhere honest to
 * point once the backend catches up.
 */
export async function runBacktest() {
    const response = await api.post(
        "/backtest/run",
    );

    return response.data;
}

export default api;
