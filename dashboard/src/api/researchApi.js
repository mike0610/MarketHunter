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

export function extractApiError(error) {
    if (axios.isAxiosError(error)) {
        return (
            error.response?.data?.detail
            || error.message
            || "API request failed."
        );
    }

    if (error instanceof Error) {
        return error.message;
    }

    return "Unknown error.";
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

export async function getLatestScan() {
    const response = await api.get(
        "/research/latest-scan",
    );

    return response.data;
}

export async function getScanRuns(params = {}) {
    const response = await api.get(
        "/research/scan-runs",
        {
            params: withoutEmptyValues(params),
        },
    );

    return response.data;
}

export async function getScanSignals(scanRunId, params = {}) {
    const response = await api.get(
        `/research/scan-runs/${scanRunId}/signals`,
        {
            params: withoutEmptyValues(params),
        },
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

export async function getResearchTradeSetup(tradeId) {
    const response = await api.get(
        `/research/trades/${tradeId}/setup`,
    );

    return response.data;
}

export async function loadResearchDashboardData() {
    const [
        statistics,
        workerStatus,
        trades,
        latestScan,
    ] = await Promise.all([
        getResearchStatistics(),
        getWorkerStatus(),
        getResearchTrades({
            limit: 100,
        }),
        getLatestScan(),
    ]);

    return {
        statistics,
        workerStatus,
        trades,
        latestScan,
    };
}

export async function loadResearchTradeDetails(tradeId) {
    const [
        tradeResult,
        setupResult,
    ] = await Promise.allSettled([
        getResearchTrade(tradeId),
        getResearchTradeSetup(tradeId),
    ]);

    const result = {
        trade: null,
        setup: null,
        tradeError: "",
        setupError: "",
    };

    if (tradeResult.status === "fulfilled") {
        result.trade = tradeResult.value;
    } else {
        result.tradeError = extractApiError(
            tradeResult.reason,
        );
    }

    if (setupResult.status === "fulfilled") {
        result.setup = setupResult.value;
    } else {
        result.setupError = extractApiError(
            setupResult.reason,
        );
    }

    return result;
}

export default api;