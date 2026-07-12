import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";

import {
    extractApiError,
    getResearchSetupReasonStatistics,
    getResearchStatistics,
} from "../api/researchApi";

import MetricCard from "../components/layout/MetricCard";
import PageHeader from "../components/layout/PageHeader";


const OUTCOME_GROUP_LABELS = {
    positive: "Positive",
    negative: "Negative",
    neutral: "Neutral",
    excluded: "Excluded",
};

const OUTCOME_GROUP_COLORS = {
    positive: "success.main",
    negative: "error.main",
    neutral: "text.primary",
    excluded: "text.secondary",
};

const OUTCOME_TYPE_LABELS = {
    take_profit: "Take Profit",
    stop_loss: "Stop Loss",
    live_stop_loss: "Live Stop Loss",
    expired_profit: "Expired (у плюсі)",
    expired_loss: "Expired (у мінусі)",
    expired_neutral: "Expired (у нулі)",
    universe_cleanup: "Universe cleanup",
    invalid_legacy: "Invalid legacy",
    open_active: "Відкрита",
    unclassified: "Не класифіковано",
};


function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }

    return Number(value).toLocaleString(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits,
        },
    );
}


function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }

    return `${Number(value).toFixed(1)}%`;
}


export default function Reports() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const [statistics, setStatistics] = useState(null);
    const [byOutcomeGroup, setByOutcomeGroup] = useState([]);
    const [byOutcome, setByOutcome] = useState([]);
    const [byStrategy, setByStrategy] = useState([]);

    const loadData = useCallback(
        async () => {
            const [
                statisticsData,
                setupReasonData,
            ] = await Promise.all([
                getResearchStatistics(),
                getResearchSetupReasonStatistics(),
            ]);

            setStatistics(statisticsData || null);
            setByOutcomeGroup(
                Array.isArray(setupReasonData?.by_outcome_group)
                    ? setupReasonData.by_outcome_group
                    : [],
            );
            setByOutcome(
                Array.isArray(setupReasonData?.by_outcome)
                    ? setupReasonData.by_outcome
                    : [],
            );
            setByStrategy(
                Array.isArray(setupReasonData?.by_strategy)
                    ? setupReasonData.by_strategy
                    : [],
            );
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

    return (
        <Box
            sx={{
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
            }}
        >
            <PageHeader
                title="Reports"
                subtitle="Чиста статистика: угоди, виключені з universe cleanup / invalid legacy, не спотворюють цифри нижче."
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

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        sm: "repeat(3, minmax(0, 1fr))",
                    },
                    mb: 3,
                }}
            >
                <MetricCard
                    label="Завершені (raw)"
                    value={formatNumber(statistics?.completed, 0)}
                />

                <MetricCard
                    label="Чисті (clean)"
                    value={formatNumber(statistics?.clean_completed, 0)}
                />

                <MetricCard
                    label="Виключено"
                    value={formatNumber(statistics?.excluded, 0)}
                    valueColor="text.secondary"
                />

                <MetricCard
                    label="Win rate (clean)"
                    value={formatPercent(statistics?.win_rate)}
                />

                <MetricCard
                    label="Profitable Expired"
                    value={formatNumber(statistics?.profitable_expired, 0)}
                    valueColor="success.main"
                />

                <MetricCard
                    label="Expired у мінусі"
                    value={formatNumber(statistics?.expired_at_loss, 0)}
                    valueColor="error.main"
                />
            </Box>

            <Typography
                variant="h6"
                fontWeight={700}
                sx={{ mb: 1.5 }}
            >
                По outcome group
            </Typography>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        sm: "repeat(4, minmax(0, 1fr))",
                    },
                    mb: 3,
                }}
            >
                {byOutcomeGroup.map((row) => (
                    <MetricCard
                        key={row.label}
                        label={OUTCOME_GROUP_LABELS[row.label] || row.label}
                        value={formatNumber(row.total, 0)}
                        caption={`${formatNumber(row.total_profit)} USDT`}
                        valueColor={OUTCOME_GROUP_COLORS[row.label]}
                    />
                ))}
            </Box>

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                    mb: 3,
                }}
            >
                <Box sx={{ p: 2, pb: 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        По outcome type
                    </Typography>
                </Box>

                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Тип</TableCell>
                                <TableCell align="right">Угод</TableCell>
                                <TableCell align="right">Win rate</TableCell>
                                <TableCell align="right">Total profit</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {byOutcome.map((row) => (
                                <TableRow key={row.label}>
                                    <TableCell>
                                        {OUTCOME_TYPE_LABELS[row.label] || row.label}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(row.total, 0)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatPercent(row.win_rate)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(row.total_profit)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            </Paper>

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                }}
            >
                <Box sx={{ p: 2, pb: 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        По стратегії (clean)
                    </Typography>
                </Box>

                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Стратегія</TableCell>
                                <TableCell align="right">Clean / Total</TableCell>
                                <TableCell align="right">Excluded</TableCell>
                                <TableCell align="right">Win rate</TableCell>
                                <TableCell align="right">Total profit</TableCell>
                                <TableCell align="right">Avg RR</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {byStrategy.map((row) => (
                                <TableRow key={row.label}>
                                    <TableCell>
                                        {row.label}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(row.clean_completed, 0)}
                                        {" / "}
                                        {formatNumber(row.total, 0)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {row.excluded > 0 ? (
                                            <Chip
                                                size="small"
                                                label={row.excluded}
                                                color="default"
                                            />
                                        ) : (
                                            "—"
                                        )}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatPercent(row.win_rate)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(row.total_profit)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(row.average_rr)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            </Paper>
        </Box>
    );
}
