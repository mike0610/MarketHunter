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
    Stack,
    Typography,
} from "@mui/material";

import { useNavigate } from "react-router-dom";

import AnalyticsIcon from "@mui/icons-material/Analytics";
import AssessmentIcon from "@mui/icons-material/Assessment";
import SearchIcon from "@mui/icons-material/Search";
import TimelineIcon from "@mui/icons-material/Timeline";

import {
    extractApiError,
    getLatestScan,
    getResearchStatistics,
    getWorkerStatus,
} from "../api/researchApi";

import MetricCard from "../components/layout/MetricCard";
import PageHeader from "../components/layout/PageHeader";


const WORKER_STATE_LABELS = {
    running: "Працює",
    waiting: "Очікує наступного циклу",
    failed: "Помилка",
    stopped: "Зупинений",
    not_started: "Не запущено",
};

const WORKER_STATE_COLORS = {
    running: "success",
    waiting: "info",
    failed: "error",
    stopped: "default",
    not_started: "default",
};


function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "—";
    }

    return date.toLocaleString("uk-UA");
}


function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }

    return `${Number(value).toFixed(1)}%`;
}


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


const QUICK_LINKS = [
    {
        label: "Scanner",
        description: "Історія сканувань ринку",
        path: "/scanner",
        icon: <SearchIcon />,
    },
    {
        label: "Signals",
        description: "Журнал сигналів по скану",
        path: "/signals",
        icon: <TimelineIcon />,
    },
    {
        label: "Research",
        description: "Virtual trades та їхня класифікація",
        path: "/research",
        icon: <AnalyticsIcon />,
    },
    {
        label: "Reports",
        description: "Чиста статистика по outcome",
        path: "/reports",
        icon: <AssessmentIcon />,
    },
];


function InfoBlock({
    label,
    value,
}) {
    return (
        <Box>
            <Typography
                variant="body2"
                color="text.secondary"
            >
                {label}
            </Typography>
            <Typography fontWeight={600}>
                {value}
            </Typography>
        </Box>
    );
}


export default function Dashboard() {
    const navigate = useNavigate();

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const [statistics, setStatistics] = useState(null);
    const [workerStatus, setWorkerStatus] = useState(null);
    const [latestScan, setLatestScan] = useState(null);

    const loadData = useCallback(
        async () => {
            const [
                statisticsData,
                workerStatusData,
                latestScanData,
            ] = await Promise.all([
                getResearchStatistics(),
                getWorkerStatus(),
                getLatestScan(),
            ]);

            setStatistics(statisticsData || null);
            setWorkerStatus(workerStatusData || null);
            setLatestScan(latestScanData?.scan_run || null);
        },
        [],
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

    const workerStateKey = String(workerStatus?.state || "").trim().toLowerCase();

    return (
        <Box
            sx={{
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
            }}
        >
            <PageHeader
                title="Dashboard"
                subtitle="Загальний стан MarketHunter: воркер, останнє сканування, чиста статистика."
            />

            {error && (
                <Alert
                    severity="warning"
                    sx={{ mb: 3 }}
                >
                    {error}
                </Alert>
            )}

            <Paper
                variant="outlined"
                sx={{
                    p: 3,
                    borderRadius: 4,
                    mb: 3,
                }}
            >
                <Stack
                    direction={{
                        xs: "column",
                        sm: "row",
                    }}
                    spacing={2}
                    sx={{
                        justifyContent: "space-between",
                        alignItems: {
                            xs: "flex-start",
                            sm: "center",
                        },
                    }}
                >
                    <Box>
                        <Typography
                            variant="h6"
                            fontWeight={700}
                        >
                            Статус воркера
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{ mt: 0.5 }}
                        >
                            Цикл №{formatNumber(workerStatus?.cycle_number, 0)}
                            {" · оновлено "}
                            {formatDateTime(workerStatus?.updated_at)}
                        </Typography>
                    </Box>

                    <Chip
                        label={
                            WORKER_STATE_LABELS[workerStateKey]
                            || "Невідомо"
                        }
                        color={
                            WORKER_STATE_COLORS[workerStateKey]
                            || "default"
                        }
                    />
                </Stack>

                {workerStatus?.last_error && (
                    <Alert
                        severity="error"
                        sx={{ mt: 2 }}
                    >
                        {workerStatus.last_error}
                    </Alert>
                )}
            </Paper>

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
                    label="Усього угод"
                    value={formatNumber(statistics?.total, 0)}
                />

                <MetricCard
                    label="Активні / очікують"
                    value={
                        `${formatNumber(statistics?.active, 0)} / `
                        + formatNumber(statistics?.waiting_entry, 0)
                    }
                />

                <MetricCard
                    label="Win rate (clean)"
                    value={formatPercent(statistics?.win_rate)}
                    caption={
                        `${formatNumber(statistics?.clean_completed, 0)} чистих `
                        + `з ${formatNumber(statistics?.completed, 0)} завершених`
                    }
                />

                <MetricCard
                    label="Виключено з чистої статистики"
                    value={formatNumber(statistics?.excluded, 0)}
                />

                <MetricCard
                    label="Profitable Expired"
                    value={formatNumber(statistics?.profitable_expired, 0)}
                    caption={
                        statistics?.profitable_expired_profit
                            ? `+${formatNumber(statistics.profitable_expired_profit)}`
                            : undefined
                    }
                    valueColor="success.main"
                />

                <MetricCard
                    label="Expired у мінусі"
                    value={formatNumber(statistics?.expired_at_loss, 0)}
                    valueColor="error.main"
                />

                <MetricCard
                    label="Total profit (clean)"
                    value={formatNumber(statistics?.total_profit)}
                    valueColor={
                        Number(statistics?.total_profit) >= 0
                            ? "success.main"
                            : "error.main"
                    }
                />

                <MetricCard
                    label="Profit factor"
                    value={
                        statistics?.profit_factor === null
                        || statistics?.profit_factor === undefined
                            ? "—"
                            : formatNumber(statistics.profit_factor)
                    }
                />
            </Box>

            <Paper
                variant="outlined"
                sx={{
                    p: 3,
                    borderRadius: 4,
                    mb: 3,
                }}
            >
                <Typography
                    variant="h6"
                    fontWeight={700}
                    sx={{ mb: 1.5 }}
                >
                    Останнє сканування
                </Typography>

                {latestScan ? (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: {
                                xs: "repeat(2, minmax(0, 1fr))",
                                sm: "repeat(4, minmax(0, 1fr))",
                            },
                        }}
                    >
                        <InfoBlock
                            label="Статус"
                            value={latestScan.status}
                        />

                        <InfoBlock
                            label="Символів проскановано"
                            value={formatNumber(latestScan.symbols_scanned, 0)}
                        />

                        <InfoBlock
                            label="Створено research-угод"
                            value={formatNumber(latestScan.research_trades_created, 0)}
                        />

                        <InfoBlock
                            label="Розпочато"
                            value={formatDateTime(latestScan.started_at)}
                        />
                    </Box>
                ) : (
                    <Typography color="text.secondary">
                        Ще жодного скану не зафіксовано.
                    </Typography>
                )}
            </Paper>

            <Typography
                variant="h6"
                fontWeight={700}
                sx={{ mb: 1.5 }}
            >
                Швидкі переходи
            </Typography>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        md: "repeat(4, minmax(0, 1fr))",
                    },
                }}
            >
                {QUICK_LINKS.map((link) => (
                    <Paper
                        key={link.path}
                        variant="outlined"
                        onClick={() => navigate(link.path)}
                        sx={{
                            p: 2.5,
                            borderRadius: 3,
                            cursor: "pointer",
                            height: "100%",
                            transition: "background-color 0.15s ease",
                            "&:hover": {
                                bgcolor: "rgba(255,255,255,0.04)",
                            },
                        }}
                    >
                        <Stack
                            direction="row"
                            spacing={1.5}
                            sx={{
                                alignItems: "center",
                                mb: 1,
                            }}
                        >
                            {link.icon}

                            <Typography
                                variant="subtitle1"
                                fontWeight={700}
                            >
                                {link.label}
                            </Typography>
                        </Stack>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            {link.description}
                        </Typography>
                    </Paper>
                ))}
            </Box>
        </Box>
    );
}
