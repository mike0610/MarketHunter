import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    FormControl,
    InputLabel,
    MenuItem,
    Paper,
    Select,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";

import RefreshIcon from "@mui/icons-material/Refresh";
import VisibilityIcon from "@mui/icons-material/Visibility";

import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    getLatestScan,
    getResearchStatistics,
    getResearchTrade,
    getResearchTrades,
    getScanSignals,
    getWorkerStatus,
} from "../api/researchApi";


const STATUS_OPTIONS = [
    {
        value: "",
        label: "Усі статуси",
    },
    {
        value: "waiting_entry",
        label: "Очікує входу",
    },
    {
        value: "active",
        label: "Активна",
    },
    {
        value: "closed",
        label: "Закрита",
    },
    {
        value: "expired",
        label: "Час вийшов",
    },
    {
        value: "candidate",
        label: "Кандидат",
    },
];

const SIGNAL_STATUS_OPTIONS = [
    {
        value: "",
        label: "Усі сигнали",
    },
    {
        value: "research",
        label: "Research",
    },
    {
        value: "elite",
        label: "Elite",
    },
    {
        value: "rejected",
        label: "Rejected",
    },
];


function getStatusLabel(status) {
    const labels = {
        candidate: "Кандидат",
        waiting_entry: "Очікує входу",
        active: "Активна",
        closed: "Закрита",
        expired: "Час вийшов",
    };

    return labels[status] || status;
}


function getStatusColor(status) {
    const colors = {
        candidate: "default",
        waiting_entry: "warning",
        active: "info",
        closed: "success",
        expired: "default",
    };

    return colors[status] || "default";
}


function getSignalStatusLabel(status) {
    const labels = {
        rejected: "Відхилено",
        research: "Research",
        elite: "Elite",
    };

    return labels[status] || status || "—";
}


function getSignalStatusColor(status) {
    const colors = {
        rejected: "default",
        research: "warning",
        elite: "success",
    };

    return colors[status] || "default";
}


function getWorkerStateLabel(state) {
    const labels = {
        not_started: "Не запускався",
        starting: "Запускається",
        running: "Виконує цикл",
        waiting: "Очікує наступного циклу",
        error: "Помилка",
        stopped: "Зупинений",
    };

    return labels[state] || state || "—";
}


function getWorkerStateColor(state) {
    const colors = {
        not_started: "default",
        starting: "info",
        running: "info",
        waiting: "success",
        error: "error",
        stopped: "warning",
    };

    return colors[state] || "default";
}


function formatPrice(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return new Intl.NumberFormat(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: 8,
        },
    ).format(value);
}


function formatMoney(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return new Intl.NumberFormat(
        "uk-UA",
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        },
    ).format(value);
}


function formatPercent(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return `${Number(value).toFixed(2)}%`;
}


function formatDate(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString("uk-UA");
}


function getProfitColor(value) {
    if (value > 0) {
        return "success.main";
    }

    if (value < 0) {
        return "error.main";
    }

    return "text.primary";
}


function getSignalReason(signal) {
    if (signal.status === "elite") {
        return "Пройшов elite-фільтр";
    }

    if (signal.status === "research") {
        return (
            signal.rejected_reason
            || "Створено virtual trade"
        );
    }

    return (
        signal.research_skipped
        || signal.rejected_reason
        || "—"
    );
}


function StatisticCard({
    label,
    value,
    color = "text.primary",
}) {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 2,
                minWidth: 170,
                border: 1,
                borderColor: "divider",
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
            >
                {label}
            </Typography>

            <Typography
                variant="h5"
                fontWeight="bold"
                color={color}
                sx={{
                    mt: 0.5,
                }}
            >
                {value}
            </Typography>
        </Paper>
    );
}


function WorkerMetric({
    label,
    value,
}) {
    return (
        <Box
            sx={{
                minWidth: 155,
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
            >
                {label}
            </Typography>

            <Typography
                variant="body1"
                fontWeight="medium"
                sx={{
                    mt: 0.5,
                }}
            >
                {value}
            </Typography>
        </Box>
    );
}


function WorkerStatusPanel({
    workerStatus,
    statistics,
}) {
    const state = workerStatus?.state || "not_started";

    return (
        <Paper
            elevation={0}
            sx={{
                p: 2,
                mb: 3,
                border: 1,
                borderColor: "divider",
            }}
        >
            <Stack
                direction={{
                    xs: "column",
                    md: "row",
                }}
                justifyContent="space-between"
                alignItems={{
                    xs: "flex-start",
                    md: "center",
                }}
                spacing={2}
                sx={{
                    mb: 2,
                }}
            >
                <Box>
                    <Typography
                        variant="h6"
                        fontWeight="bold"
                    >
                        Статус воркера
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                            mt: 0.5,
                        }}
                    >
                        Цикл №{workerStatus?.cycle_number ?? 0}
                    </Typography>
                </Box>

                <Chip
                    label={getWorkerStateLabel(state)}
                    color={getWorkerStateColor(state)}
                />
            </Stack>

            <Stack
                direction="row"
                flexWrap="wrap"
                gap={3}
            >
                <WorkerMetric
                    label="Останній цикл"
                    value={formatDate(
                        workerStatus?.last_cycle_finished_at,
                    )}
                />

                <WorkerMetric
                    label="Наступний запуск"
                    value={formatDate(
                        workerStatus?.next_cycle_at,
                    )}
                />

                <WorkerMetric
                    label="Очікують входу"
                    value={statistics?.waiting_entry ?? "—"}
                />

                <WorkerMetric
                    label="Активні угоди"
                    value={statistics?.active ?? "—"}
                />

                <WorkerMetric
                    label="Оновлено"
                    value={formatDate(
                        workerStatus?.updated_at,
                    )}
                />
            </Stack>

            {state === "not_started" && (
                <Alert
                    severity="info"
                    sx={{
                        mt: 2,
                    }}
                >
                    Воркер ще не запускався. Запусти
                    {" "}
                    <strong>python -m app.worker</strong>
                    {" "}
                    у окремому терміналі.
                </Alert>
            )}

            {workerStatus?.last_error && (
                <Alert
                    severity="error"
                    sx={{
                        mt: 2,
                    }}
                >
                    Остання помилка воркера:
                    {" "}
                    {workerStatus.last_error}
                </Alert>
            )}
        </Paper>
    );
}


function ScanJournalPanel({
    latestScan,
    scanSignals,
    scanSignalsTotal,
    signalStatus,
    setSignalStatus,
    loading,
}) {
    const scanRun = latestScan?.scan_run || null;

    return (
        <Paper
            elevation={0}
            sx={{
                p: 2,
                mb: 3,
                border: 1,
                borderColor: "divider",
            }}
        >
            <Stack
                direction={{
                    xs: "column",
                    md: "row",
                }}
                justifyContent="space-between"
                alignItems={{
                    xs: "flex-start",
                    md: "center",
                }}
                spacing={2}
                sx={{
                    mb: 2,
                }}
            >
                <Box>
                    <Typography
                        variant="h6"
                        fontWeight="bold"
                    >
                        Останнє сканування
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                            mt: 0.5,
                        }}
                    >
                        Журнал усіх знайдених сетапів:
                        rejected / research / elite.
                    </Typography>
                </Box>

                <Stack
                    direction="row"
                    spacing={1}
                    alignItems="center"
                >
                    <Chip
                        label={
                            scanRun
                                ? scanRun.status
                                : "немає сканів"
                        }
                        color={
                            scanRun?.status === "completed"
                                ? "success"
                                : "default"
                        }
                    />

                    <FormControl
                        size="small"
                        sx={{
                            minWidth: 155,
                        }}
                    >
                        <InputLabel id="signal-status-label">
                            Сигнали
                        </InputLabel>

                        <Select
                            labelId="signal-status-label"
                            label="Сигнали"
                            value={signalStatus}
                            onChange={(event) => {
                                setSignalStatus(
                                    event.target.value,
                                );
                            }}
                        >
                            {SIGNAL_STATUS_OPTIONS.map(
                                (option) => (
                                    <MenuItem
                                        key={option.value}
                                        value={option.value}
                                    >
                                        {option.label}
                                    </MenuItem>
                                ),
                            )}
                        </Select>
                    </FormControl>
                </Stack>
            </Stack>

            {!scanRun && (
                <Alert severity="info">
                    Ще немає записаного сканування.
                    Запусти один цикл:
                    {" "}
                    <strong>python -m app.main</strong>
                </Alert>
            )}

            {scanRun && (
                <>
                    <Stack
                        direction="row"
                        flexWrap="wrap"
                        gap={3}
                        sx={{
                            mb: 2,
                        }}
                    >
                        <WorkerMetric
                            label="Початок"
                            value={formatDate(
                                scanRun.started_at,
                            )}
                        />

                        <WorkerMetric
                            label="Завершено"
                            value={formatDate(
                                scanRun.finished_at,
                            )}
                        />

                        <WorkerMetric
                            label="TF"
                            value={scanRun.timeframe}
                        />

                        <WorkerMetric
                            label="Перевірено пар"
                            value={scanRun.symbols_scanned}
                        />

                        <WorkerMetric
                            label="Кандидатів"
                            value={scanRun.candidate_signals}
                        />

                        <WorkerMetric
                            label="Research trades"
                            value={
                                scanRun.research_trades_created
                            }
                        />

                        <WorkerMetric
                            label="Elite signals"
                            value={scanRun.elite_signals_found}
                        />

                        <WorkerMetric
                            label="Показано"
                            value={
                                `${scanSignals.length}/${scanSignalsTotal}`
                            }
                        />
                    </Stack>

                    {scanRun.error && (
                        <Alert
                            severity="error"
                            sx={{
                                mb: 2,
                            }}
                        >
                            Помилка сканування: {scanRun.error}
                        </Alert>
                    )}

                    <TableContainer
                        sx={{
                            maxHeight: 430,
                        }}
                    >
                        <Table
                            stickyHeader
                            size="small"
                        >
                            <TableHead>
                                <TableRow>
                                    <TableCell>
                                        Символ
                                    </TableCell>

                                    <TableCell>
                                        Стратегія
                                    </TableCell>

                                    <TableCell>
                                        Напрямок
                                    </TableCell>

                                    <TableCell>
                                        Probability
                                    </TableCell>

                                    <TableCell>
                                        Score
                                    </TableCell>

                                    <TableCell>
                                        Entry
                                    </TableCell>

                                    <TableCell>
                                        SL
                                    </TableCell>

                                    <TableCell>
                                        TP
                                    </TableCell>

                                    <TableCell>
                                        RR
                                    </TableCell>

                                    <TableCell>
                                        Статус
                                    </TableCell>

                                    <TableCell>
                                        Причина
                                    </TableCell>
                                </TableRow>
                            </TableHead>

                            <TableBody>
                                {loading && (
                                    <TableRow>
                                        <TableCell
                                            colSpan={11}
                                            align="center"
                                            sx={{
                                                py: 4,
                                            }}
                                        >
                                            <CircularProgress
                                                size={24}
                                            />
                                        </TableCell>
                                    </TableRow>
                                )}

                                {!loading
                                    && scanSignals.length === 0 && (
                                    <TableRow>
                                        <TableCell
                                            colSpan={11}
                                            align="center"
                                            sx={{
                                                py: 4,
                                            }}
                                        >
                                            Немає сигналів за
                                            вибраним фільтром.
                                        </TableCell>
                                    </TableRow>
                                )}

                                {!loading
                                    && scanSignals.map((signal) => (
                                    <TableRow
                                        hover
                                        key={signal.id}
                                    >
                                        <TableCell>
                                            <Typography
                                                fontWeight="bold"
                                            >
                                                {signal.symbol}
                                            </Typography>
                                        </TableCell>

                                        <TableCell>
                                            {signal.strategy}
                                        </TableCell>

                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={
                                                    signal.direction
                                                }
                                                color={
                                                    signal.direction
                                                    === "LONG"
                                                        ? "success"
                                                        : "error"
                                                }
                                            />
                                        </TableCell>

                                        <TableCell>
                                            {signal.probability === null
                                                ? "—"
                                                : `${signal.probability}%`}
                                        </TableCell>

                                        <TableCell>
                                            {signal.score}
                                        </TableCell>

                                        <TableCell>
                                            {formatPrice(
                                                signal.entry_price,
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            {formatPrice(
                                                signal.stop_loss,
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            {formatPrice(
                                                signal.take_profit,
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            {signal.risk_reward ?? "—"}
                                        </TableCell>

                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={getSignalStatusLabel(
                                                    signal.status,
                                                )}
                                                color={getSignalStatusColor(
                                                    signal.status,
                                                )}
                                            />
                                        </TableCell>

                                        <TableCell
                                            sx={{
                                                maxWidth: 320,
                                            }}
                                        >
                                            <Typography
                                                variant="body2"
                                                color="text.secondary"
                                            >
                                                {getSignalReason(signal)}
                                            </Typography>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </>
            )}
        </Paper>
    );
}


function DetailRow({
    label,
    value,
}) {
    return (
        <Box
            sx={{
                display: "flex",
                justifyContent: "space-between",
                gap: 3,
                py: 0.75,
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
            >
                {label}
            </Typography>

            <Typography
                variant="body2"
                textAlign="right"
            >
                {value}
            </Typography>
        </Box>
    );
}


export default function Research() {
    const [statistics, setStatistics] = useState(null);
    const [workerStatus, setWorkerStatus] =
        useState(null);

    const [latestScan, setLatestScan] = useState(null);
    const [scanSignals, setScanSignals] = useState([]);
    const [scanSignalsTotal, setScanSignalsTotal] =
        useState(0);

    const [trades, setTrades] = useState([]);

    const [status, setStatus] = useState("");
    const [symbol, setSymbol] = useState("");
    const [signalStatus, setSignalStatus] = useState("");

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const [selectedTrade, setSelectedTrade] =
        useState(null);

    const [detailLoading, setDetailLoading] =
        useState(false);

    const loadResearchData = useCallback(
        async () => {
            setLoading(true);
            setError("");

            try {
                const [
                    statisticsData,
                    tradesData,
                    workerStatusData,
                    latestScanData,
                ] = await Promise.all([
                    getResearchStatistics(),
                    getResearchTrades({
                        status,
                        symbol,
                        limit: 100,
                    }),
                    getWorkerStatus(),
                    getLatestScan(),
                ]);

                setStatistics(statisticsData);
                setTrades(tradesData.trades);
                setWorkerStatus(workerStatusData);
                setLatestScan(latestScanData);

                const scanRunId =
                    latestScanData?.scan_run?.id;

                if (!scanRunId) {
                    setScanSignals([]);
                    setScanSignalsTotal(0);
                    return;
                }

                const scanSignalsData = await getScanSignals(
                    scanRunId,
                    {
                        status: signalStatus,
                        limit: 200,
                    },
                );

                setScanSignals(scanSignalsData.signals);
                setScanSignalsTotal(scanSignalsData.total);
            } catch (requestError) {
                const message =
                    requestError.response?.data?.detail
                    || requestError.message
                    || (
                        "Не вдалося завантажити "
                        + "дані Research API."
                    );

                setError(message);
            } finally {
                setLoading(false);
            }
        },
        [
            status,
            symbol,
            signalStatus,
        ],
    );

    useEffect(() => {
        void loadResearchData();
    }, [loadResearchData]);

    async function handleOpenTrade(tradeId) {
        setDetailLoading(true);

        try {
            const trade = await getResearchTrade(
                tradeId,
            );

            setSelectedTrade(trade);
        } catch (requestError) {
            const message =
                requestError.response?.data?.detail
                || requestError.message
                || "Не вдалося завантажити деталі угоди.";

            setError(message);
        } finally {
            setDetailLoading(false);
        }
    }

    function handleCloseDialog() {
        setSelectedTrade(null);
    }

    return (
        <Box>
            <Stack
                direction={{
                    xs: "column",
                    md: "row",
                }}
                justifyContent="space-between"
                alignItems={{
                    xs: "flex-start",
                    md: "center",
                }}
                spacing={2}
                sx={{
                    mb: 3,
                }}
            >
                <Box>
                    <Typography
                        variant="h4"
                        fontWeight="bold"
                    >
                        Research Trades
                    </Typography>

                    <Typography
                        variant="body1"
                        color="text.secondary"
                        sx={{
                            mt: 0.5,
                        }}
                    >
                        Virtual trades, статистика,
                        журнал сканувань та результати
                        перевірки сигналів.
                    </Typography>
                </Box>

                <Button
                    variant="contained"
                    startIcon={<RefreshIcon />}
                    onClick={loadResearchData}
                    disabled={loading}
                >
                    Оновити
                </Button>
            </Stack>

            {error && (
                <Alert
                    severity="error"
                    sx={{
                        mb: 3,
                    }}
                    onClose={() => setError("")}
                >
                    {error}
                </Alert>
            )}

            <WorkerStatusPanel
                workerStatus={workerStatus}
                statistics={statistics}
            />

            <ScanJournalPanel
                latestScan={latestScan}
                scanSignals={scanSignals}
                scanSignalsTotal={scanSignalsTotal}
                signalStatus={signalStatus}
                setSignalStatus={setSignalStatus}
                loading={loading}
            />

            <Stack
                direction="row"
                flexWrap="wrap"
                gap={2}
                sx={{
                    mb: 3,
                }}
            >
                <StatisticCard
                    label="Усього угод"
                    value={statistics?.total ?? "—"}
                />

                <StatisticCard
                    label="Очікують входу"
                    value={
                        statistics?.waiting_entry
                        ?? "—"
                    }
                    color="warning.main"
                />

                <StatisticCard
                    label="Активні"
                    value={statistics?.active ?? "—"}
                    color="info.main"
                />

                <StatisticCard
                    label="Завершені"
                    value={
                        statistics?.completed
                        ?? "—"
                    }
                    color="success.main"
                />

                <StatisticCard
                    label="Win rate"
                    value={formatPercent(
                        statistics?.win_rate,
                    )}
                />

                <StatisticCard
                    label="PnL"
                    value={`${formatMoney(
                        statistics?.total_profit,
                    )} USDT`}
                    color={getProfitColor(
                        statistics?.total_profit,
                    )}
                />
            </Stack>

            <Paper
                elevation={0}
                sx={{
                    p: 2,
                    mb: 3,
                    border: 1,
                    borderColor: "divider",
                }}
            >
                <Stack
                    direction={{
                        xs: "column",
                        md: "row",
                    }}
                    spacing={2}
                    alignItems={{
                        xs: "stretch",
                        md: "center",
                    }}
                >
                    <FormControl
                        size="small"
                        sx={{
                            minWidth: 210,
                        }}
                    >
                        <InputLabel id="research-status-label">
                            Статус
                        </InputLabel>

                        <Select
                            labelId="research-status-label"
                            label="Статус"
                            value={status}
                            onChange={(event) => {
                                setStatus(
                                    event.target.value,
                                );
                            }}
                        >
                            {STATUS_OPTIONS.map(
                                (option) => (
                                    <MenuItem
                                        key={option.value}
                                        value={option.value}
                                    >
                                        {option.label}
                                    </MenuItem>
                                ),
                            )}
                        </Select>
                    </FormControl>

                    <TextField
                        size="small"
                        label="Символ"
                        placeholder="BTCUSDT"
                        value={symbol}
                        onChange={(event) => {
                            setSymbol(
                                event.target.value,
                            );
                        }}
                        sx={{
                            minWidth: 210,
                        }}
                    />

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        Показано угод: {trades.length}
                    </Typography>
                </Stack>
            </Paper>

            <Paper
                elevation={0}
                sx={{
                    border: 1,
                    borderColor: "divider",
                    overflow: "hidden",
                }}
            >
                <TableContainer>
                    <Table
                        stickyHeader
                        size="small"
                    >
                        <TableHead>
                            <TableRow>
                                <TableCell>
                                    Символ
                                </TableCell>

                                <TableCell>
                                    Стратегія
                                </TableCell>

                                <TableCell>
                                    Напрямок
                                </TableCell>

                                <TableCell>
                                    TF
                                </TableCell>

                                <TableCell>
                                    Ймовірність
                                </TableCell>

                                <TableCell>
                                    Вхід
                                </TableCell>

                                <TableCell>
                                    SL
                                </TableCell>

                                <TableCell>
                                    TP
                                </TableCell>

                                <TableCell>
                                    Статус
                                </TableCell>

                                <TableCell>
                                    Створено
                                </TableCell>

                                <TableCell align="right">
                                    Деталі
                                </TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {loading && (
                                <TableRow>
                                    <TableCell
                                        colSpan={11}
                                        align="center"
                                        sx={{
                                            py: 5,
                                        }}
                                    >
                                        <CircularProgress
                                            size={28}
                                        />
                                    </TableCell>
                                </TableRow>
                            )}

                            {!loading
                                && trades.length === 0 && (
                                <TableRow>
                                    <TableCell
                                        colSpan={11}
                                        align="center"
                                        sx={{
                                            py: 5,
                                        }}
                                    >
                                        Немає угод за
                                        вибраними фільтрами.
                                    </TableCell>
                                </TableRow>
                            )}

                            {!loading
                                && trades.map((trade) => (
                                <TableRow
                                    hover
                                    key={trade.id}
                                >
                                    <TableCell>
                                        <Typography
                                            fontWeight="bold"
                                        >
                                            {trade.symbol}
                                        </Typography>
                                    </TableCell>

                                    <TableCell>
                                        {trade.strategy}
                                    </TableCell>

                                    <TableCell>
                                        <Chip
                                            size="small"
                                            label={
                                                trade.direction
                                            }
                                            color={
                                                trade.direction
                                                === "LONG"
                                                    ? "success"
                                                    : "error"
                                            }
                                        />
                                    </TableCell>

                                    <TableCell>
                                        {trade.timeframe}
                                    </TableCell>

                                    <TableCell>
                                        {trade.probability}%
                                    </TableCell>

                                    <TableCell>
                                        {formatPrice(
                                            trade.entry_price,
                                        )}
                                    </TableCell>

                                    <TableCell>
                                        {formatPrice(
                                            trade.stop_loss,
                                        )}
                                    </TableCell>

                                    <TableCell>
                                        {formatPrice(
                                            trade.take_profit,
                                        )}
                                    </TableCell>

                                    <TableCell>
                                        <Chip
                                            size="small"
                                            label={getStatusLabel(
                                                trade.status,
                                            )}
                                            color={getStatusColor(
                                                trade.status,
                                            )}
                                        />
                                    </TableCell>

                                    <TableCell>
                                        {formatDate(
                                            trade.created_at,
                                        )}
                                    </TableCell>

                                    <TableCell align="right">
                                        <Button
                                            size="small"
                                            startIcon={
                                                <VisibilityIcon />
                                            }
                                            onClick={() => {
                                                void handleOpenTrade(
                                                    trade.id,
                                                );
                                            }}
                                            disabled={
                                                detailLoading
                                            }
                                        >
                                            Відкрити
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            </Paper>

            <Dialog
                open={Boolean(selectedTrade)}
                onClose={handleCloseDialog}
                fullWidth
                maxWidth="sm"
            >
                <DialogTitle>
                    {selectedTrade
                        ? (
                            `${selectedTrade.symbol} — `
                            + selectedTrade.direction
                        )
                        : "Деталі угоди"}
                </DialogTitle>

                <DialogContent dividers>
                    {selectedTrade && (
                        <Stack spacing={2}>
                            <Box>
                                <Stack
                                    direction="row"
                                    spacing={1}
                                    alignItems="center"
                                >
                                    <Chip
                                        label={getStatusLabel(
                                            selectedTrade.status,
                                        )}
                                        color={getStatusColor(
                                            selectedTrade.status,
                                        )}
                                    />

                                    <Chip
                                        label={
                                            selectedTrade.strategy
                                        }
                                        variant="outlined"
                                    />
                                </Stack>
                            </Box>

                            <Divider />

                            <Box>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        mb: 1,
                                    }}
                                >
                                    Параметри входу
                                </Typography>

                                <DetailRow
                                    label="Entry"
                                    value={formatPrice(
                                        selectedTrade.entry_price,
                                    )}
                                />

                                <DetailRow
                                    label="Stop Loss"
                                    value={formatPrice(
                                        selectedTrade.stop_loss,
                                    )}
                                />

                                <DetailRow
                                    label="Take Profit"
                                    value={formatPrice(
                                        selectedTrade.take_profit,
                                    )}
                                />

                                <DetailRow
                                    label="Ймовірність"
                                    value={
                                        `${selectedTrade.probability}%`
                                    }
                                />

                                <DetailRow
                                    label="Score"
                                    value={selectedTrade.score}
                                />

                                <DetailRow
                                    label="Notional"
                                    value={`${formatMoney(
                                        selectedTrade.notional,
                                    )} USDT`}
                                />
                            </Box>

                            <Divider />

                            <Box>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        mb: 1,
                                    }}
                                >
                                    Результат
                                </Typography>

                                <DetailRow
                                    label="PnL"
                                    value={`${formatMoney(
                                        selectedTrade.profit_amount,
                                    )} USDT`}
                                />

                                <DetailRow
                                    label="PnL %"
                                    value={formatPercent(
                                        selectedTrade.profit_percent,
                                    )}
                                />

                                <DetailRow
                                    label="RR"
                                    value={Number(
                                        selectedTrade.rr,
                                    ).toFixed(2)}
                                />

                                <DetailRow
                                    label="Максимальний прибуток"
                                    value={formatPercent(
                                        selectedTrade.max_profit_percent,
                                    )}
                                />

                                <DetailRow
                                    label="Максимальна просадка"
                                    value={formatPercent(
                                        selectedTrade.max_drawdown_percent,
                                    )}
                                />
                            </Box>

                            <Divider />

                            <Box>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        mb: 1,
                                    }}
                                >
                                    Час
                                </Typography>

                                <DetailRow
                                    label="Створено"
                                    value={formatDate(
                                        selectedTrade.created_at,
                                    )}
                                />

                                <DetailRow
                                    label="Відкрито"
                                    value={formatDate(
                                        selectedTrade.opened_at,
                                    )}
                                />

                                <DetailRow
                                    label="Закрито"
                                    value={formatDate(
                                        selectedTrade.closed_at,
                                    )}
                                />

                                <DetailRow
                                    label="Причина закриття"
                                    value={
                                        selectedTrade.close_reason
                                        || "—"
                                    }
                                />
                            </Box>

                            <Divider />

                            <Box>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        mb: 1,
                                    }}
                                >
                                    Причини сигналу
                                </Typography>

                                {selectedTrade.reasons.length === 0 ? (
                                    <Typography
                                        variant="body2"
                                        color="text.secondary"
                                    >
                                        Причини відсутні.
                                    </Typography>
                                ) : (
                                    <Stack spacing={0.75}>
                                        {selectedTrade.reasons.map(
                                            (
                                                reason,
                                                index,
                                            ) => (
                                                <Typography
                                                    key={
                                                        `${reason}-${index}`
                                                    }
                                                    variant="body2"
                                                >
                                                    • {reason}
                                                </Typography>
                                            ),
                                        )}
                                    </Stack>
                                )}
                            </Box>
                        </Stack>
                    )}
                </DialogContent>

                <DialogActions>
                    <Button onClick={handleCloseDialog}>
                        Закрити
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}