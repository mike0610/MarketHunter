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


function formatSignedNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }

    const numeric = Number(value);
    const formatted = Math.abs(numeric).toLocaleString(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits,
        },
    );

    if (numeric > 0) {
        return `+${formatted}`;
    }

    if (numeric < 0) {
        return `-${formatted}`;
    }

    return formatted;
}


function signedColor(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "text.secondary";
    }

    if (Number(value) > 0) {
        return "success.main";
    }

    if (Number(value) < 0) {
        return "error.main";
    }

    return "text.primary";
}


function formatOrDashIfEmptySample(cleanCompleted, value, formatter) {
    if (!cleanCompleted || Number(cleanCompleted) <= 0) {
        return "—";
    }

    return formatter(value);
}


function formatTopStrategies(strategies, limit = 3) {
    if (!strategies || typeof strategies !== "object") {
        return "—";
    }

    const entries = Object.entries(strategies)
        .filter(([, count]) => Number(count) > 0)
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .slice(0, limit);

    if (entries.length === 0) {
        return "—";
    }

    return entries
        .map(([name, count]) => `${name || "Unknown"} ${formatNumber(count, 0)}`)
        .join(", ");
}


function formatDirections(directions) {
    const long = Number(directions?.LONG || 0);
    const short = Number(directions?.SHORT || 0);

    return `LONG ${formatNumber(long, 0)} / SHORT ${formatNumber(short, 0)}`;
}


function firstExample(examples) {
    if (!Array.isArray(examples) || examples.length === 0) {
        return "";
    }

    return String(examples[0] || "");
}


function truncateText(text, maxLength = 70) {
    if (!text) {
        return "—";
    }

    return text.length > maxLength
        ? `${text.slice(0, maxLength)}…`
        : text;
}


function sortGroupedRows(rows) {
    return [...rows].sort(
        (a, b) => {
            const cleanDiff = Number(b.clean_completed || 0) - Number(a.clean_completed || 0);

            if (cleanDiff !== 0) {
                return cleanDiff;
            }

            return Number(b.total_profit || 0) - Number(a.total_profit || 0);
        },
    );
}


export default function Reports() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [statisticsError, setStatisticsError] = useState("");
    const [setupReasonError, setSetupReasonError] = useState("");

    const [statistics, setStatistics] = useState(null);
    const [byOutcomeGroup, setByOutcomeGroup] = useState([]);
    const [byOutcome, setByOutcome] = useState([]);
    const [byStrategy, setByStrategy] = useState([]);
    const [bySetupReason, setBySetupReason] = useState([]);
    const [signalBlockReasons, setSignalBlockReasons] = useState([]);

    const loadData = useCallback(
        async () => {
            setStatisticsError("");
            setSetupReasonError("");

            const [
                statisticsResult,
                setupReasonResult,
            ] = await Promise.allSettled([
                getResearchStatistics(),
                getResearchSetupReasonStatistics(),
            ]);

            if (statisticsResult.status === "fulfilled") {
                setStatistics(statisticsResult.value || null);
            } else {
                setStatistics(null);
                setStatisticsError(extractApiError(statisticsResult.reason));
            }

            if (setupReasonResult.status === "fulfilled") {
                const setupReasonData = setupReasonResult.value;

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
                        ? sortGroupedRows(setupReasonData.by_strategy)
                        : [],
                );
                setBySetupReason(
                    Array.isArray(setupReasonData?.by_setup_reason)
                        ? sortGroupedRows(setupReasonData.by_setup_reason)
                        : [],
                );
                setSignalBlockReasons(
                    Array.isArray(setupReasonData?.signal_block_reasons)
                        ? [...setupReasonData.signal_block_reasons].sort(
                            (a, b) => Number(b.count || 0) - Number(a.count || 0),
                        )
                        : [],
                );
            } else {
                setByOutcomeGroup([]);
                setByOutcome([]);
                setByStrategy([]);
                setBySetupReason([]);
                setSignalBlockReasons([]);
                setSetupReasonError(extractApiError(setupReasonResult.reason));
            }
        },
        [],
    );

    const handleRefresh = useCallback(
        async () => {
            try {
                setRefreshing(true);
                await loadData();
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

            {statisticsError && (
                <Alert
                    severity="warning"
                    sx={{ mb: 3 }}
                >
                    Не вдалося завантажити загальну статистику: {statisticsError}
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
                <MetricCard
                    label="Total profit (clean)"
                    value={formatSignedNumber(statistics?.total_profit)}
                    caption="USDT"
                    valueColor={signedColor(statistics?.total_profit)}
                />

                <MetricCard
                    label="Profit factor"
                    value={formatNumber(statistics?.profit_factor)}
                />

                <MetricCard
                    label="Average profit"
                    value={formatSignedNumber(statistics?.average_profit)}
                    caption="% / угоду"
                    valueColor={signedColor(statistics?.average_profit)}
                />

                <MetricCard
                    label="Average RR"
                    value={formatNumber(statistics?.average_rr)}
                />
            </Box>

            <Typography
                variant="h6"
                fontWeight={700}
                sx={{ mb: 1.5 }}
            >
                По outcome group
            </Typography>

            {setupReasonError ? (
                <Alert
                    severity="warning"
                    sx={{ mb: 3 }}
                >
                    Не вдалося завантажити групову статистику: {setupReasonError}
                </Alert>
            ) : (
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
                    {byOutcomeGroup.length === 0 ? (
                        <Typography
                            color="text.secondary"
                            sx={{ gridColumn: "1 / -1" }}
                        >
                            Ще немає статистики за результатами
                        </Typography>
                    ) : (
                        byOutcomeGroup.map((row) => (
                            <MetricCard
                                key={row.label}
                                label={OUTCOME_GROUP_LABELS[row.label] || row.label}
                                value={formatNumber(row.total, 0)}
                                caption={`${formatNumber(row.total_profit)} USDT`}
                                valueColor={OUTCOME_GROUP_COLORS[row.label]}
                            />
                        ))
                    )}
                </Box>
            )}

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                    mb: 3,
                }}
            >
                <Box sx={{ p: 2, pb: setupReasonError ? 2 : 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        По outcome type
                    </Typography>
                </Box>

                {setupReasonError ? (
                    <Box sx={{ px: 2, pb: 2 }}>
                        <Alert severity="warning">
                            Не вдалося завантажити дані: {setupReasonError}
                        </Alert>
                    </Box>
                ) : (
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
                                {byOutcome.length === 0 ? (
                                    <TableRow>
                                        <TableCell
                                            colSpan={4}
                                            align="center"
                                            sx={{ color: "text.secondary", py: 3 }}
                                        >
                                            Ще немає статистики за результатами
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    byOutcome.map((row) => (
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
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>
                )}
            </Paper>

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                }}
            >
                <Box sx={{ p: 2, pb: setupReasonError ? 2 : 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        По стратегії (clean)
                    </Typography>
                </Box>

                {setupReasonError ? (
                    <Box sx={{ px: 2, pb: 2 }}>
                        <Alert severity="warning">
                            Не вдалося завантажити дані: {setupReasonError}
                        </Alert>
                    </Box>
                ) : (
                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Стратегія</TableCell>
                                <TableCell align="right">Clean / Total</TableCell>
                                <TableCell align="right">Excluded</TableCell>
                                <TableCell align="right">W / L / BE</TableCell>
                                <TableCell align="right">Profitable expired</TableCell>
                                <TableCell align="right">Win rate</TableCell>
                                <TableCell align="right">Total profit</TableCell>
                                <TableCell align="right">Avg RR</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {byStrategy.length === 0 ? (
                                <TableRow>
                                    <TableCell
                                        colSpan={8}
                                        align="center"
                                        sx={{ color: "text.secondary", py: 3 }}
                                    >
                                        Недостатньо даних для порівняння стратегій
                                    </TableCell>
                                </TableRow>
                            ) : (
                                byStrategy.map((row) => (
                                    <TableRow key={row.label}>
                                        <TableCell>
                                            {row.label || "Unknown"}
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
                                            {formatNumber(row.wins, 0)}
                                            {" / "}
                                            {formatNumber(row.losses, 0)}
                                            {" / "}
                                            {formatNumber(row.breakeven, 0)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatNumber(row.profitable_expired, 0)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatOrDashIfEmptySample(
                                                row.clean_completed,
                                                row.win_rate,
                                                formatPercent,
                                            )}
                                        </TableCell>

                                        <TableCell
                                            align="right"
                                            sx={{ color: signedColor(row.total_profit) }}
                                        >
                                            {formatSignedNumber(row.total_profit)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatOrDashIfEmptySample(
                                                row.clean_completed,
                                                row.average_rr,
                                                formatNumber,
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
                )}
            </Paper>

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                    mt: 3,
                }}
            >
                <Box sx={{ p: 2, pb: setupReasonError ? 2 : 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        Performance by setup
                    </Typography>
                </Box>

                {setupReasonError ? (
                    <Box sx={{ px: 2, pb: 2 }}>
                        <Alert severity="warning">
                            Не вдалося завантажити дані: {setupReasonError}
                        </Alert>
                    </Box>
                ) : (
                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Setup</TableCell>
                                <TableCell align="right">Clean / Total</TableCell>
                                <TableCell align="right">Excluded</TableCell>
                                <TableCell align="right">W / L / BE</TableCell>
                                <TableCell align="right">Profitable expired</TableCell>
                                <TableCell align="right">Win rate</TableCell>
                                <TableCell align="right">Total profit</TableCell>
                                <TableCell align="right">Avg RR</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {bySetupReason.length === 0 ? (
                                <TableRow>
                                    <TableCell
                                        colSpan={8}
                                        align="center"
                                        sx={{ color: "text.secondary", py: 3 }}
                                    >
                                        Ще немає статистики за setup
                                    </TableCell>
                                </TableRow>
                            ) : (
                                bySetupReason.map((row, index) => (
                                    <TableRow key={row.label || `setup-${index}`}>
                                        <TableCell>
                                            {row.label || "Unknown"}
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
                                            {formatNumber(row.wins, 0)}
                                            {" / "}
                                            {formatNumber(row.losses, 0)}
                                            {" / "}
                                            {formatNumber(row.breakeven, 0)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatNumber(row.profitable_expired, 0)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatOrDashIfEmptySample(
                                                row.clean_completed,
                                                row.win_rate,
                                                formatPercent,
                                            )}
                                        </TableCell>

                                        <TableCell
                                            align="right"
                                            sx={{ color: signedColor(row.total_profit) }}
                                        >
                                            {formatSignedNumber(row.total_profit)}
                                        </TableCell>

                                        <TableCell align="right">
                                            {formatOrDashIfEmptySample(
                                                row.clean_completed,
                                                row.average_rr,
                                                formatNumber,
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
                )}
            </Paper>

            <Paper
                variant="outlined"
                sx={{
                    borderRadius: 4,
                    overflow: "hidden",
                    mt: 3,
                }}
            >
                <Box sx={{ p: 2, pb: setupReasonError ? 2 : 0 }}>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        Signal rejection reasons
                    </Typography>
                </Box>

                {setupReasonError ? (
                    <Box sx={{ px: 2, pb: 2 }}>
                        <Alert severity="warning">
                            Не вдалося завантажити дані: {setupReasonError}
                        </Alert>
                    </Box>
                ) : (
                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Reason</TableCell>
                                <TableCell align="right">Count</TableCell>
                                <TableCell>Strategies</TableCell>
                                <TableCell align="right">LONG / SHORT</TableCell>
                                <TableCell>Example</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {signalBlockReasons.length === 0 ? (
                                <TableRow>
                                    <TableCell
                                        colSpan={5}
                                        align="center"
                                        sx={{ color: "text.secondary", py: 3 }}
                                    >
                                        Причини блокування поки не зафіксовані
                                    </TableCell>
                                </TableRow>
                            ) : (
                                signalBlockReasons.map((row, index) => {
                                    const example = firstExample(row.examples);

                                    return (
                                        <TableRow key={row.label || `reason-${index}`}>
                                            <TableCell sx={{ maxWidth: 220 }}>
                                                {row.label || "Unknown"}
                                            </TableCell>

                                            <TableCell align="right">
                                                {formatNumber(row.count, 0)}
                                            </TableCell>

                                            <TableCell sx={{ maxWidth: 260 }}>
                                                {formatTopStrategies(row.strategies)}
                                            </TableCell>

                                            <TableCell align="right">
                                                {formatDirections(row.directions)}
                                            </TableCell>

                                            <TableCell
                                                title={example || undefined}
                                                sx={{
                                                    maxWidth: 320,
                                                    whiteSpace: "nowrap",
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                }}
                                            >
                                                {truncateText(example)}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
                )}
            </Paper>
        </Box>
    );
}
