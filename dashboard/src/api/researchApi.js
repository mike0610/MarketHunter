import axios from "axios";

const api = axios.create({
    baseURL: (
        import.meta.env.VITE_API_BASE_URL
        || "http://127.0.0.1:8000"
    ),
});

function withoutEmptyValues(params = {}) {
    return Object.fromEntries(
        Object.entries(params).filter(
            ([, value]) => (
                value !== ""
                && value !== null
                && value !== undefined
            ),
        ),
    );
}

export async function getResearchStatistics() {
    const response = await api.get(
        "/research/statistics",
    );

    return response.data;
}

export async function getWorkerStatus() {
    const response = await api.get(
        "/research/worker-status",
    );

    return response.data;
}

export async function getResearchTrades(params = {}) {
    const response = await api.get(
        "/research/trades",
        {
            params: withoutEmptyValues(params),
        },
    );

    return response.data;
}

export async function getResearchTrade(tradeId) {
    const response = await api.get(
        `/research/trades/${tradeId}`,
    );

    return response.data;
}