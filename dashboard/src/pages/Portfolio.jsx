import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    Alert,
    Box,
    CircularProgress,
    Paper,
    Typography,
} from "@mui/material";

import { extractApiError } from "../api/researchApi";
import { getPortfolioStatus } from "../api/portfolioApi";

import MetricCard from "../components/layout/MetricCard";
import PageHeader from "../components/layout/PageHeader";


export default function Portfolio() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [status, setStatus] = useState(null);

    const loadData = useCallback(
        async () => {
            const data = await getPortfolioStatus();

            setStatus(data || null);
        },
        [],
    );

    const handleRefresh = useCallback(
        async () => {
            try {
                setRefreshing(true);
                setError("");
                await loadData();
            } catch (refreshError) {
                setError(extractApiError(refreshError));
            } finally {
                setRefreshing(false);
                setLoading(false);
            }
        },
        [
            loadData,
        ],
    );

    useEffect(
        () => {
            let active = true;

            async function start() {
                try {
                    await loadData();
                } catch (loadError) {
                    if (active) {
                        setError(extractApiError(loadError));
                    }
                } finally {
                    if (active) {
                        setLoading(false);
                    }
                }
            }

            void start();

            return () => {
                active = false;
            };
        },
        [
            loadData,
        ],
    );

    if (loading) {
        return (
            <Box
                sx={{
                    minHeight: "60vh",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                }}
            >
                <CircularProgress />
            </Box>
        );
    }

    const positions = Array.isArray(status?.positions) ? status.positions : [];

    return (
        <Box
            sx={{
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
            }}
        >
            <PageHeader
                title="Portfolio"
                subtitle="Реальні позиції, ризик, PnL. Поки в розробці (Portfolio v1)."
                onRefresh={handleRefresh}
                refreshing={refreshing}
            />

            {error && (
                <Alert
                    severity="warning"
                    sx={{ mb: 3 }}
                >
                    {error}
                </Alert>
            )}

            <Alert
                severity="info"
                sx={{ mb: 3 }}
            >
                Portfolio v1 ще не реалізовано на бекенді — `/portfolio/status`
                зараз повертає заглушку (баланс, equity і позиції завжди
                нульові/порожні). Нижче — саме те, що реально повертає API,
                без вигаданих чисел.
            </Alert>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                    },
                    mb: 3,
                }}
            >
                <MetricCard
                    label="Баланс"
                    value={status?.balance ?? "—"}
                />

                <MetricCard
                    label="Equity"
                    value={status?.equity ?? "—"}
                />
            </Box>

            <Paper
                variant="outlined"
                sx={{
                    p: 4,
                    borderRadius: 4,
                    textAlign: "center",
                }}
            >
                {positions.length === 0 ? (
                    <Typography color="text.secondary">
                        Немає відкритих позицій (модуль ще не підключено до
                        реальних даних).
                    </Typography>
                ) : (
                    <Typography color="text.secondary">
                        {positions.length} позицій.
                    </Typography>
                )}
            </Paper>
        </Box>
    );
}
