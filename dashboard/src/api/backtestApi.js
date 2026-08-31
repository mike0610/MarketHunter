import axios from "axios";

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
});

export async function runBacktest(payload) {
    const response = await api.post("/backtest/run", payload);
    return response.data;
}

export async function runStrategyBacktest(payload) {
    const response = await api.post("/backtest/run/strategy", payload);
    return response.data;
}

export async function listBacktests() {
    const response = await api.get("/backtest/results");
    return response.data;
}

export async function getBacktest(backtestId) {
    const response = await api.get(`/backtest/results/${backtestId}`);
    return response.data;
}

export default api;
