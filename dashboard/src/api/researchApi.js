import axios from "axios";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000";

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10_000,
});

export async function getResearchStatistics() {
    const response = await apiClient.get(
        "/research/statistics",
    );

    return response.data;
}

export async function getResearchTrades({
    status = "",
    symbol = "",
    limit = 100,
    offset = 0,
} = {}) {
    const params = {
        limit,
        offset,
    };

    if (status) {
        params.status = status;
    }

    if (symbol.trim()) {
        params.symbol = symbol.trim().toUpperCase();
    }

    const response = await apiClient.get(
        "/research/trades",
        {
            params,
        },
    );

    return response.data;
}

export async function getResearchTrade(
    tradeId,
) {
    const response = await apiClient.get(
        `/research/trades/${tradeId}`,
    );

    return response.data;
}