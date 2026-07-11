import {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
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
    GlobalStyles,
    MenuItem,
    Paper,
    Select,
    Stack,
    Typography,
} from "@mui/material";

import RefreshIcon from "@mui/icons-material/Refresh";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";

import {
    extractApiError,
    getResearchStatistics,
    getResearchTrades,
    getWorkerStatus,
    loadResearchTradeDetails,
} from "../api/researchApi";

import SetupVisualization from "../components/SetupVisualization";


function safeArray(value) {
    return Array.isArray(value) ? value : [];
}


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


function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || value === "") {
        return "—";
    }

    const numeric = Number(value);

    if (!Number.isFinite(numeric)) {
        return "—";
    }

    return numeric.toLocaleString(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits,
        },
    );
}


function formatPrice(value) {
    if (value === null || value === undefined || value === "") {
        return "—";
    }

    const numeric = Number(value);

    if (!Number.isFinite(numeric)) {
        return "—";
    }

    return numeric.toLocaleString(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: 8,
        },
    );
}


function formatPercentValue(value) {
    if (value === null || value === undefined || value === "") {
        return "";
    }

    const numeric = Number(value);

    if (!Number.isFinite(numeric)) {
        return "";
    }

    return `${formatNumber(numeric, 2)}%`;
}


function compactCloseReason(value) {
    const reason = String(value || "").trim();

    if (!reason) {
        return "";
    }

    return reason
        .replace(/^LIVE_/i, "")
        .split("_")
        .join(" ")
        .toLowerCase()
        .replace(/\b\w/g, (char) => char.toUpperCase());
}



function normalizeWorkerState(value) {
    const normalized = String(value || "").trim().toLowerCase();

    if (normalized === "running") {
        return "running";
    }

    if (normalized === "waiting") {
        return "waiting";
    }

    if (normalized === "failed" || normalized === "error") {
        return "failed";
    }

    if (normalized === "stopped") {
        return "stopped";
    }

    return "unknown";
}


function workerStateLabel(value) {
    switch (normalizeWorkerState(value)) {
        case "running":
            return "Працює";
        case "waiting":
            return "Очікує наступного циклу";
        case "failed":
            return "Помилка";
        case "stopped":
            return "Зупинений";
        default:
            return "Невідомо";
    }
}


function workerStateColor(value) {
    switch (normalizeWorkerState(value)) {
        case "running":
            return "info";
        case "waiting":
            return "success";
        case "failed":
            return "error";
        case "stopped":
            return "warning";
        default:
            return "default";
    }
}


function normalizeTradeStatus(value) {
    const normalized = String(value || "").trim().toLowerCase();

    if (normalized === "waiting_entry") {
        return "waiting_entry";
    }

    if (normalized === "active") {
        return "active";
    }

    if (normalized === "closed") {
        return "closed";
    }

    if (normalized === "expired") {
        return "expired";
    }

    return "unknown";
}


function tradeStatusLabel(value) {
    switch (normalizeTradeStatus(value)) {
        case "waiting_entry":
            return "Очікує входу";
        case "active":
            return "Активна";
        case "closed":
            return "Закрита";
        case "expired":
            return "Протермінована";
        default:
            return "Невідомо";
    }
}


function tradeStatusColor(value) {
    switch (normalizeTradeStatus(value)) {
        case "waiting_entry":
            return "warning";
        case "active":
            return "info";
        case "closed":
            return "success";
        case "expired":
            return "default";
        default:
            return "default";
    }
}


function numericPrice(value) {
    const numeric = Number(value);

    return Number.isFinite(numeric)
        ? numeric
        : null;
}


function isNearPrice(left, right) {
    if (left === null || right === null) {
        return false;
    }

    const tolerance = Math.max(
        Math.abs(right) * 0.00001,
        0.00000001,
    );

    return Math.abs(left - right) <= tolerance;
}


function activeStopManagementState(trade) {
    const direction = normalizeDirection(trade?.direction);
    const entry = numericPrice(trade?.entry_price);
    const stopLoss = numericPrice(trade?.stop_loss);

    if (entry === null || stopLoss === null) {
        return {
            label: "Initial SL",
            color: "info",
            variant: "outlined",
        };
    }

    if (direction === "SHORT") {
        if (stopLoss < entry && !isNearPrice(stopLoss, entry)) {
            return {
                label: "Profit lock",
                color: "success",
                variant: "filled",
            };
        }

        if (stopLoss <= entry || isNearPrice(stopLoss, entry)) {
            return {
                label: "BE moved",
                color: "success",
                variant: "outlined",
            };
        }

        return {
            label: "Initial SL",
            color: "info",
            variant: "outlined",
        };
    }

    if (stopLoss > entry && !isNearPrice(stopLoss, entry)) {
        return {
            label: "Profit lock",
            color: "success",
            variant: "filled",
        };
    }

    if (stopLoss >= entry || isNearPrice(stopLoss, entry)) {
        return {
            label: "BE moved",
            color: "success",
            variant: "outlined",
        };
    }

    return {
        label: "Initial SL",
        color: "info",
        variant: "outlined",
    };
}


function oneRPercentFromTrade(trade) {
    const entry = numericPrice(trade?.entry_price);
    const takeProfit = numericPrice(trade?.take_profit);

    if (entry === null || takeProfit === null || entry === 0) {
        return null;
    }

    const oneRDistance = Math.abs(takeProfit - entry) / 2;
    const oneRPercent = oneRDistance / Math.abs(entry) * 100;

    return Number.isFinite(oneRPercent) && oneRPercent > 0
        ? oneRPercent
        : null;
}


function tradeRProgress(trade) {
    const oneRPercent = oneRPercentFromTrade(trade);
    const maxProfit = Number(trade?.max_profit_percent);

    if (
        oneRPercent === null
        || !Number.isFinite(maxProfit)
    ) {
        return null;
    }

    return maxProfit / oneRPercent;
}


function formatTradeRProgress(trade) {
    const progress = tradeRProgress(trade);

    if (progress === null) {
        return "—";
    }

    return `${formatNumber(progress, 2)}R`;
}


function tradeRiskReward(trade) {
    const directValue = Number(
        trade?.rr
        ?? trade?.risk_reward
        ?? trade?.riskReward
    );

    if (Number.isFinite(directValue) && directValue > 0) {
        return directValue;
    }

    const entry = numericPrice(trade?.entry_price);
    const stopLoss = numericPrice(trade?.stop_loss);
    const takeProfit = numericPrice(trade?.take_profit);

    if (entry === null || stopLoss === null || takeProfit === null) {
        return null;
    }

    const risk = Math.abs(entry - stopLoss);
    const reward = Math.abs(takeProfit - entry);

    if (risk <= 0) {
        return null;
    }

    const rr = reward / risk;

    return Number.isFinite(rr) && rr > 0
        ? rr
        : null;
}


function formatTradeRiskReward(trade) {
    const rr = tradeRiskReward(trade);

    if (rr === null) {
        return "—";
    }

    return formatNumber(rr, 2);
}


function formatOneRDistance(trade) {
    const oneRPercent = oneRPercentFromTrade(trade);

    if (oneRPercent === null) {
        return "—";
    }

    return formatPercentValue(oneRPercent);
}


function tradeManagementState(trade) {
    const status = normalizeTradeStatus(trade?.status);
    const closeReason = String(trade?.close_reason || "").toUpperCase();

    if (status === "waiting_entry") {
        return {
            label: "Waiting entry",
            color: "warning",
            variant: "outlined",
        };
    }

    if (status === "expired") {
        return {
            label: "Expired",
            color: "default",
            variant: "outlined",
        };
    }

    if (status === "active") {
        return activeStopManagementState(trade);
    }

    if (status === "closed") {
        if (closeReason.includes("TAKE_PROFIT")) {
            return {
                label: "TP closed",
                color: "success",
                variant: "filled",
            };
        }

        if (closeReason.includes("PROFIT_LOCK")) {
            return {
                label: "Profit lock closed",
                color: "success",
                variant: "filled",
            };
        }

        if (closeReason.includes("BREAKEVEN")) {
            return {
                label: "BE closed",
                color: "info",
                variant: "outlined",
            };
        }

        if (closeReason.includes("STOP_LOSS")) {
            return {
                label: "SL closed",
                color: "error",
                variant: "filled",
            };
        }

        return {
            label: "Closed",
            color: "success",
            variant: "outlined",
        };
    }

    return {
        label: "Unknown",
        color: "default",
        variant: "outlined",
    };
}


function normalizeDirection(value) {
    return String(value || "LONG").trim().toUpperCase();
}


function directionColor(value) {
    return normalizeDirection(value) === "SHORT"
        ? "error"
        : "success";
}


function normalizeResearchGroup(value) {
    const normalized = String(value || "").trim().toLowerCase();

    if (normalized === "experimental") {
        return "experimental";
    }

    return "core";
}


function tradeResearchGroup(trade) {
    return normalizeResearchGroup(
        trade?.research_group
        || (
            trade?.is_experimental
                ? "experimental"
                : "core"
        ),
    );
}


function researchGroupLabel(value) {
    return normalizeResearchGroup(value) === "experimental"
        ? "EXPERIMENTAL"
        : "CORE";
}


function researchGroupColor(value) {
    return normalizeResearchGroup(value) === "experimental"
        ? "secondary"
        : "primary";
}


function normalizeExperimentTag(value) {
    const normalized = String(value || "").trim();

    return normalized || "";
}


function normalizeNumberKey(value) {
    if (value === null || value === undefined || value === "") {
        return "none";
    }

    const numeric = Number(value);

    if (!Number.isFinite(numeric)) {
        return String(value);
    }

    return numeric.toFixed(8);
}

function MetricCard({
    label,
    value,
}) {
    return (
        <Paper
            variant="outlined"
            sx={{
                p: 2,
                borderRadius: 3,
                minWidth: 0,
                bgcolor: "rgba(255,255,255,0.02)",
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                    wordBreak: "break-word",
                }}
            >
                {label}
            </Typography>

            <Typography
                variant="h5"
                fontWeight={700}
                sx={{
                    mt: 1,
                    wordBreak: "break-word",
                }}
            >
                {value}
            </Typography>
        </Paper>
    );
}


function InfoStat({
    label,
    value,
}) {
    return (
        <Box
            sx={{
                minWidth: 0,
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                    wordBreak: "break-word",
                }}
            >
                {label}
            </Typography>

            <Typography
                variant="body1"
                fontWeight={600}
                sx={{
                    mt: 0.5,
                    wordBreak: "break-word",
                    whiteSpace: "normal",
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
    return (
        <Paper
            variant="outlined"
            sx={{
                p: 3,
                borderRadius: 4,
                mb: 3,
                minWidth: 0,
            }}
        >
            <Stack
                direction={{
                    xs: "column",
                    lg: "row",
                }}
                justifyContent="space-between"
                alignItems={{
                    xs: "flex-start",
                    lg: "center",
                }}
                spacing={1.5}
                sx={{
                    mb: 2,
                }}
            >
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="h4"
                        fontWeight={700}
                    >
                        Статус воркера
                    </Typography>

                    <Typography
                        variant="h6"
                        sx={{
                            mt: 1,
                        }}
                    >
                        Цикл №{workerStatus?.cycle_number ?? "—"}
                    </Typography>
                </Box>

                <Chip
                    color={workerStateColor(workerStatus?.state)}
                    label={workerStateLabel(workerStatus?.state)}
                />
            </Stack>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(5, minmax(0, 1fr))",
                    },
                }}
            >
                <InfoStat
                    label="Останній цикл"
                    value={formatDateTime(
                        workerStatus?.last_cycle_finished_at,
                    )}
                />

                <InfoStat
                    label="Наступний запуск"
                    value={formatDateTime(
                        workerStatus?.next_cycle_at,
                    )}
                />

                <InfoStat
                    label="Очікують входу"
                    value={String(statistics?.waiting_entry ?? "0")}
                />

                <InfoStat
                    label="Активні угоди"
                    value={String(statistics?.active ?? "0")}
                />

                <InfoStat
                    label="Оновлено"
                    value={formatDateTime(
                        workerStatus?.updated_at,
                    )}
                />
            </Box>

            {workerStatus?.last_error && (
                <Alert
                    severity="warning"
                    sx={{
                        mt: 2,
                    }}
                >
                    {workerStatus.last_error}
                </Alert>
            )}
        </Paper>
    );
}


function TradeCard({
    trade,
    onOpen,
}) {
    const managementState = tradeManagementState(trade);

    return (
        <Paper
            variant="outlined"
            sx={{
                p: 2,
                borderRadius: 3,
                minWidth: 0,
            }}
        >
            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    minWidth: 0,
                }}
            >
                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    flexWrap="wrap"
                    alignItems="center"
                    sx={{
                        minWidth: 0,
                    }}
                >
                    <Typography
                        variant="h6"
                        fontWeight={700}
                        sx={{
                            wordBreak: "break-word",
                        }}
                    >
                        {trade.symbol}
                    </Typography>

                    <Chip
                        size="small"
                        color={directionColor(trade.direction)}
                        label={trade.direction}
                    />

                    <Chip
                        size="small"
                        color={tradeStatusColor(trade.status)}
                        label={tradeStatusLabel(trade.status)}
                    />

                    <Chip
                        size="small"
                        color={managementState.color}
                        variant={managementState.variant}
                        label={managementState.label}
                    />

                    <Chip
                        size="small"
                        variant="outlined"
                        color="info"
                        label={String(
                            trade.market || "market",
                        ).toUpperCase()}
                    />

                    <Chip
                        size="small"
                        color={researchGroupColor(
                            tradeResearchGroup(trade),
                        )}
                        variant={
                            tradeResearchGroup(trade) === "experimental"
                                ? "filled"
                                : "outlined"
                        }
                        label={researchGroupLabel(
                            tradeResearchGroup(trade),
                        )}
                    />

                    {normalizeExperimentTag(trade.experiment_tag) && (
                        <Chip
                            size="small"
                            variant="outlined"
                            color="secondary"
                            label={normalizeExperimentTag(
                                trade.experiment_tag,
                            )}
                        />
                    )}

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        {trade.strategy} · {trade.timeframe}
                    </Typography>
                </Stack>

                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: {
                            xs: "1fr",
                            lg: "minmax(0, 1fr) 170px",
                        },
                        gap: 2,
                        alignItems: "stretch",
                        minWidth: 0,
                    }}
                >
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: {
                                xs: "repeat(2, minmax(0, 1fr))",
                                sm: "repeat(3, minmax(0, 1fr))",
                                md: "repeat(4, minmax(0, 1fr))",
                                xl: "repeat(5, minmax(0, 1fr))",
                            },
                            alignItems: "start",
                            minWidth: 0,
                        }}
                    >
                        <InfoStat
                            label="Entry"
                            value={formatPrice(trade.entry_price)}
                        />

                        <InfoStat
                            label="SL"
                            value={formatPrice(trade.stop_loss)}
                        />

                        <InfoStat
                            label="TP"
                            value={formatPrice(trade.take_profit)}
                        />

                        <InfoStat
                            label="Probability"
                            value={`${formatNumber(trade.probability, 0)}%`}
                        />

                        <InfoStat
                            label="RR"
                            value={formatTradeRiskReward(trade)}
                        />

                        <InfoStat
                            label="PnL"
                            value={`${formatNumber(trade.profit_amount, 2)} USDT`}
                        />

                        <InfoStat
                            label="Max profit"
                            value={formatPercentValue(trade.max_profit_percent)}
                        />

                        <InfoStat
                            label="Max drawdown"
                            value={formatPercentValue(trade.max_drawdown_percent)}
                        />

                        <InfoStat
                            label="Close reason"
                            value={compactCloseReason(trade.close_reason)}
                        />

                        <InfoStat
                            label="Opened"
                            value={formatDateTime(trade.opened_at)}
                        />

                        <InfoStat
                            label="Closed"
                            value={formatDateTime(trade.closed_at)}
                        />

                        <InfoStat
                            label="R progress"
                            value={formatTradeRProgress(trade)}
                        />

                        <InfoStat
                            label="1R distance"
                            value={formatOneRDistance(trade)}
                        />

                        <InfoStat
                            label="BE trigger"
                            value="1.00R"
                        />

                        <InfoStat
                            label="Profit lock"
                            value="1.50R"
                        />
                    </Box>

                    <Box
                        sx={{
                            display: "flex",
                            alignItems: {
                                xs: "stretch",
                                lg: "center",
                            },
                            justifyContent: {
                                xs: "stretch",
                                lg: "flex-end",
                            },
                            minWidth: 0,
                        }}
                    >
                        <Button
                            variant="outlined"
                            startIcon={<VisibilityOutlinedIcon />}
                            onClick={() => onOpen(trade)}
                            fullWidth
                            sx={{
                                minHeight: 44,
                                minWidth: 0,
                                whiteSpace: "nowrap",
                            }}
                        >
                            Відкрити
                        </Button>
                    </Box>
                </Box>
            </Box>
        </Paper>
    );
}


function countTradesByResearchGroup(trades, group) {
    return trades.filter(
        (trade) => tradeResearchGroup(trade) === group,
    ).length;
}


function countTradesByMarket(trades, market) {
    return trades.filter(
        (trade) => String(trade.market || "").toLowerCase() === market,
    ).length;
}


function TradeSection({
    title,
    subtitle,
    trades,
    onOpen,
    defaultExpanded = false,
}) {
    return (
        <Accordion
            defaultExpanded={defaultExpanded}
            disableGutters
            sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 3,
                bgcolor: "background.paper",
                overflow: "hidden",
                "&:before": {
                    display: "none",
                },
            }}
        >
            <AccordionSummary
                expandIcon={(
                    <Box
                        component="span"
                        sx={{
                            color: "text.secondary",
                            fontSize: 22,
                            lineHeight: 1,
                        }}
                    >
                        
                    </Box>
                )}
                sx={{
                    px: 2,
                    py: 1,
                    minHeight: 72,
                    "& .MuiAccordionSummary-content": {
                        my: 1,
                    },
                }}
            >
                <Box
                    sx={{
                        flex: 1,
                        minWidth: 0,
                        pr: 2,
                    }}
                >
                    <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        flexWrap="wrap"
                    >
                        <Typography
                            variant="h6"
                            fontWeight={800}
                        >
                            {title}
                        </Typography>

                        <Chip
                            label={formatNumber(
                                trades.length,
                                0,
                            )}
                            size="small"
                            color={defaultExpanded ? "primary" : "default"}
                            variant={defaultExpanded ? "filled" : "outlined"}
                        />
                    </Stack>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                            mt: 0.5,
                        }}
                    >
                        {subtitle}
                    </Typography>
                </Box>
            </AccordionSummary>

            <AccordionDetails
                sx={{
                    px: 2,
                    pt: 0,
                    pb: 2,
                }}
            >
                <Stack spacing={2}>
                    {trades.map((trade) => (
                        <TradeCard
                            key={trade.id}
                            trade={trade}
                            onOpen={onOpen}
                        />
                    ))}
                </Stack>
            </AccordionDetails>
        </Accordion>
    );
}


export default function Research() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const [statistics, setStatistics] = useState(null);
    const [workerStatus, setWorkerStatus] = useState(null);
    const [trades, setTrades] = useState([]);


    const [tradeResearchFilter, setTradeResearchFilter] = useState("all");

    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogLoading, setDialogLoading] = useState(false);
    const [dialogError, setDialogError] = useState("");
    const [selectedTrade, setSelectedTrade] = useState(null);
    const [selectedSetup, setSelectedSetup] = useState(null);
    const [selectedSetupError, setSelectedSetupError] = useState("");

    const loadData = useCallback(
        async () => {
            setError("");

            const [
                statisticsData,
                workerStatusData,
                tradesData,
            ] = await Promise.all([
                getResearchStatistics(),
                getWorkerStatus(),
                getResearchTrades({
                    limit: 100,
                }),
            ]);

            setStatistics(statisticsData || null);
            setWorkerStatus(workerStatusData || null);
            setTrades(safeArray(tradesData?.trades));
        },
        [],
    );

    const handleRefresh = useCallback(
        async () => {
            try {
                setRefreshing(true);
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

    const filteredTrades = useMemo(
        () => trades.filter((trade) => (
            tradeResearchFilter === "all"
            || tradeResearchGroup(trade) === tradeResearchFilter
        )),
        [
            trades,
            tradeResearchFilter,
        ],
    );

    const tradeSections = useMemo(
        () => {
            const definitions = [
                {
                    key: "active",
                    title: "Active trades",
                    subtitle: "Угоди, які вже активовані й зараз у ринку.",
                },
                {
                    key: "waiting_entry",
                    title: "Waiting entry",
                    subtitle: "Сетапи створені, але entry ще не активований.",
                },
                {
                    key: "closed",
                    title: "Closed / completed",
                    subtitle: "Закриті, завершені або протерміновані research-угоди.",
                },
                {
                    key: "other",
                    title: "Other",
                    subtitle: "Угоди з нестандартним або невідомим статусом.",
                },
            ];

            const grouped = new Map(
                definitions.map((definition) => [
                    definition.key,
                    [],
                ]),
            );

            filteredTrades.forEach((trade) => {
                const status = normalizeTradeStatus(trade.status);
                const key = status === "expired"
                    ? "closed"
                    : grouped.has(status)
                        ? status
                        : "other";

                grouped.get(key).push(trade);
            });

            return definitions
                .map((definition) => ({
                    ...definition,
                    trades: grouped.get(definition.key),
                }))
                .filter((section) => section.trades.length > 0);
        },
        [
            filteredTrades,
        ],
    );


    const coreTradeCount = useMemo(
        () => trades.filter(
            (trade) => tradeResearchGroup(trade) === "core",
        ).length,
        [
            trades,
        ],
    );

    const experimentalTradeCount = useMemo(
        () => trades.filter(
            (trade) => tradeResearchGroup(trade) === "experimental",
        ).length,
        [
            trades,
        ],
    );

    const spotResearchTradeCount = useMemo(
        () => trades.filter(
            (trade) => normalizeExperimentTag(
                trade.experiment_tag,
            ) === "spot_research",
        ).length,
        [
            trades,
        ],
    );

    const handleCloseDialog = useCallback(
        () => {
            setDialogOpen(false);
            setDialogLoading(false);
            setDialogError("");
            setSelectedTrade(null);
            setSelectedSetup(null);
            setSelectedSetupError("");
        },
        [],
    );

    const handleOpenTrade = useCallback(
        async (trade) => {
            if (!trade?.id) {
                return;
            }

            setDialogOpen(true);
            setDialogLoading(true);
            setDialogError("");
            setSelectedTrade(trade);
            setSelectedSetup(null);
            setSelectedSetupError("");

            try {
                const details = await loadResearchTradeDetails(
                    trade.id,
                );

                if (details.trade) {
                    setSelectedTrade(details.trade);
                }

                if (details.setup) {
                    setSelectedSetup(details.setup);
                }

                if (details.tradeError) {
                    setDialogError(details.tradeError);
                }

                if (details.setupError) {
                    setSelectedSetupError(details.setupError);
                }
            } catch (detailsError) {
                setDialogError(extractApiError(detailsError));
            } finally {
                setDialogLoading(false);
            }
        },
        [],
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
                overflowX: "hidden",
            }}
        >
            <GlobalStyles
                styles={{
                    body: {
                        overflowX: "hidden",
                    },
                    "#root": {
                        overflowX: "hidden",
                    },
                    ".MuiSelect-select": {
                        fontSize: "0.9rem",
                        paddingTop: "9px",
                        paddingBottom: "9px",
                    },
                    ".MuiMenuItem-root": {
                        fontSize: "0.9rem",
                    },
                }}
            />

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
                        position: "relative",
                        width: "100%",
                        pr: { md: 24 },
                    mb: 3,
                }}
            >
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="h3"
                        fontWeight={700}
                    >
                        Research Trades
                    </Typography>

                    <Typography
                        variant="body1"
                        fontWeight={400}
                        color="text.secondary"
                        sx={{
                            mt: 1,
                            wordBreak: "break-word",
                        }}
                    >
                        Virtual trades, статистика та setup-аналіз.
                    </Typography>
                </Box>

                <Button
                    variant="contained"
                    size="medium"
                    startIcon={
                        refreshing
                            ? (
                                <CircularProgress
                                    size={18}
                                    color="inherit"
                                />
                            )
                            : <RefreshIcon />
                    }
                    onClick={handleRefresh}
                    disabled={refreshing}
                    sx={{
                        minWidth: {
                            xs: "100%",
                            sm: 150,
                        },
                        height: 44,
                        px: 2.5,
                        borderRadius: 3,
                        position: {
                            xs: "static",
                            md: "absolute",
                        },
                        right: {
                            md: 0,
                        },
                        top: {
                            md: 40,
                        },
                        whiteSpace: "nowrap",
                    }}
                >
                    {refreshing ? "Оновлення..." : "ОНОВИТИ"}
                </Button>
            </Stack>

            {error && (
                <Alert
                    severity="error"
                    sx={{
                        mb: 3,
                        width: "100%",
                    }}
                >
                    {error}
                </Alert>
            )}

            <WorkerStatusPanel
                workerStatus={workerStatus}
                statistics={statistics}
            />
<Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(6, minmax(0, 1fr))",
                    },
                    mb: 3,
                }}
            >
                <MetricCard
                    label="Усього угод"
                    value={formatNumber(statistics?.total, 0)}
                />

                <MetricCard
                    label="Очікують входу"
                    value={formatNumber(statistics?.waiting_entry, 0)}
                />

                <MetricCard
                    label="Активні"
                    value={formatNumber(statistics?.active, 0)}
                />

                <MetricCard
                    label="Завершені"
                    value={formatNumber(statistics?.completed, 0)}
                />

                <MetricCard
                    label="Win rate"
                    value={`${formatNumber(statistics?.win_rate, 2)}%`}
                />

                <MetricCard
                    label="PnL"
                    value={`${formatNumber(statistics?.total_profit, 2)} USDT`}
                />
            </Box>

            <Paper
                variant="outlined"
                sx={{
                    p: 3,
                    borderRadius: 4,
                    minWidth: 0,
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
                    <Box sx={{ minWidth: 0 }}>
                        <Typography
                            variant="h4"
                            fontWeight={700}
                        >
                            Virtual trades
                        </Typography>

                        <Typography
                            variant="body1"
                            color="text.secondary"
                            sx={{
                                mt: 1,
                                wordBreak: "break-word",
                            }}
                        >
                            Натисни “Відкрити”, щоб подивитися
                            повні деталі й setup-аналіз.
                        </Typography>
                    </Box>

                    <Chip
                        color="info"
                        label={`Угод: ${filteredTrades.length}/${trades.length}`}
                    />
                </Stack>

                <Stack
                    direction={{
                        xs: "column",
                        sm: "row",
                    }}
                    spacing={1.5}
                    useFlexGap
                    flexWrap="wrap"
                    alignItems={{
                        xs: "stretch",
                        sm: "center",
                    }}
                    sx={{
                        mb: 2,
                    }}
                >
                    <FormControl
                        size="small"
                        sx={{
                            minWidth: {
                                xs: "100%",
                                sm: 190,
                            },
                        }}
                    >
                        <Select
                            value={tradeResearchFilter}
                            onChange={(event) => {
                                setTradeResearchFilter(
                                    event.target.value,
                                );
                            }}
                        >
                            <MenuItem value="all">
                                Усі research-групи
                            </MenuItem>

                            <MenuItem value="core">
                                Core
                            </MenuItem>

                            <MenuItem value="experimental">
                                Experimental
                            </MenuItem>
                        </Select>
                    </FormControl>

                    <Chip
                        size="small"
                        color="primary"
                        variant={
                            tradeResearchFilter === "core"
                                ? "filled"
                                : "outlined"
                        }
                        label={`Core: ${coreTradeCount}`}
                        onClick={() => {
                            setTradeResearchFilter("core");
                        }}
                    />

                    <Chip
                        size="small"
                        color="secondary"
                        variant={
                            tradeResearchFilter === "experimental"
                                ? "filled"
                                : "outlined"
                        }
                        label={`Experimental: ${experimentalTradeCount}`}
                        onClick={() => {
                            setTradeResearchFilter("experimental");
                        }}
                    />

                    <Chip
                        size="small"
                        color="secondary"
                        variant="outlined"
                        label={`spot_research: ${spotResearchTradeCount}`}
                        onClick={() => {
                            setTradeResearchFilter("experimental");
                        }}
                    />

                    <Button
                        variant="outlined"
                        size="small"
                        onClick={() => {
                            setTradeResearchFilter("all");
                        }}
                        disabled={tradeResearchFilter === "all"}
                        sx={{
                            height: 40,
                            minHeight: 40,
                            whiteSpace: "nowrap",
                            fontSize: "0.82rem",
                            alignSelf: {
                                xs: "stretch",
                                sm: "center",
                            },
                        }}
                    >
                        Reset trades
                    </Button>
                </Stack>

                <Stack spacing={2}>
                    {filteredTrades.length === 0 ? (
                        <Paper
                            variant="outlined"
                            sx={{
                                p: 3,
                                borderRadius: 3,
                                textAlign: "center",
                            }}
                        >
                            <Typography
                                variant="body1"
                                color="text.secondary"
                            >
                                Угод поки що немає.
                            </Typography>
                        </Paper>
                    ) : (
                        tradeSections.map((section) => (
                            <TradeSection
                                key={section.key}
                                title={section.title}
                                subtitle={section.subtitle}
                                trades={section.trades}
                                onOpen={handleOpenTrade}
                                defaultExpanded={
                                    section.key === "active"
                                    || section.key === "waiting_entry"
                                }
                            />
                        ))
                    )}
                </Stack>
            </Paper>

            <Dialog
                open={dialogOpen}
                onClose={handleCloseDialog}
                fullWidth
                maxWidth="lg"
            >
                <DialogTitle>
                    {selectedTrade
                        ? `${selectedTrade.symbol} — ${selectedTrade.direction}`
                        : "Деталі угоди"}
                </DialogTitle>

                <DialogContent dividers>
                    {dialogLoading ? (
                        <Box
                            sx={{
                                py: 6,
                                display: "flex",
                                justifyContent: "center",
                            }}
                        >
                            <CircularProgress />
                        </Box>
                    ) : (
                        <Box sx={{ minWidth: 0 }}>
                            {dialogError && (
                                <Alert
                                    severity="warning"
                                    sx={{
                                        mb: 2,
                                    }}
                                >
                                    <Box
                                        component="pre"
                                        sx={{
                                            m: 0,
                                            fontFamily: "inherit",
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                        }}
                                    >
                                        {dialogError}
                                    </Box>
                                </Alert>
                            )}

                            {selectedTrade ? (
                                <>
                                    <Stack
                                        direction="row"
                                        spacing={1}
                                        useFlexGap
                                        flexWrap="wrap"
                                        alignItems="center"
                                        sx={{
                                            mb: 2,
                                        }}
                                    >
                                        <Chip
                                            color={tradeStatusColor(
                                                selectedTrade.status,
                                            )}
                                            label={tradeStatusLabel(
                                                selectedTrade.status,
                                            )}
                                        />

                                        <Chip
                                            color={tradeManagementState(
                                                selectedTrade,
                                            ).color}
                                            variant={tradeManagementState(
                                                selectedTrade,
                                            ).variant}
                                            label={tradeManagementState(
                                                selectedTrade,
                                            ).label}
                                        />

                                        <Chip
                                            color={directionColor(
                                                selectedTrade.direction,
                                            )}
                                            label={selectedTrade.direction}
                                        />

                                        <Chip
                                            variant="outlined"
                                            label={selectedTrade.strategy}
                                        />

                                        <Chip
                                            variant="outlined"
                                            color="info"
                                            label={String(
                                                selectedTrade.market
                                                || "market",
                                            ).toUpperCase()}
                                        />

                                        <Chip
                                            color={researchGroupColor(
                                                tradeResearchGroup(selectedTrade),
                                            )}
                                            variant={
                                                tradeResearchGroup(selectedTrade)
                                                === "experimental"
                                                    ? "filled"
                                                    : "outlined"
                                            }
                                            label={researchGroupLabel(
                                                tradeResearchGroup(selectedTrade),
                                            )}
                                        />

                                        {normalizeExperimentTag(
                                            selectedTrade.experiment_tag,
                                        ) && (
                                            <Chip
                                                variant="outlined"
                                                color="secondary"
                                                label={normalizeExperimentTag(
                                                    selectedTrade.experiment_tag,
                                                )}
                                            />
                                        )}
                                    </Stack>

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
                                        <InfoStat
                                            label="Entry"
                                            value={formatPrice(
                                                selectedTrade.entry_price,
                                            )}
                                        />

                                        <InfoStat
                                            label="Stop Loss"
                                            value={formatPrice(
                                                selectedTrade.stop_loss,
                                            )}
                                        />

                                        <InfoStat
                                            label="Take Profit"
                                            value={formatPrice(
                                                selectedTrade.take_profit,
                                            )}
                                        />

                                        <InfoStat
                                            label="Probability"
                                            value={
                                                `${formatNumber(
                                                    selectedTrade.probability,
                                                    0,
                                                )}%`
                                            }
                                        />

                                        <InfoStat
                                            label="Score"
                                            value={formatNumber(
                                                selectedTrade.score,
                                                0,
                                            )}
                                        />

                                        <InfoStat
                                            label="Notional"
                                            value={
                                                `${formatNumber(
                                                    selectedTrade.notional,
                                                    2,
                                                )} USDT`
                                            }
                                        />

                                        <InfoStat
                                            label="PnL"
                                            value={
                                                `${formatNumber(
                                                    selectedTrade.profit_amount,
                                                    2,
                                                )} USDT`
                                            }
                                        />

                                        <InfoStat
                                            label="RR"
                                            value={formatTradeRiskReward(selectedTrade)}
                                        />

                                        <InfoStat
                                            label="Створено"
                                            value={formatDateTime(
                                                selectedTrade.created_at,
                                            )}
                                        />

                                        <InfoStat
                                            label="Відкрито"
                                            value={formatDateTime(
                                                selectedTrade.opened_at,
                                            )}
                                        />

                                        <InfoStat
                                            label="Закрито"
                                            value={formatDateTime(
                                                selectedTrade.closed_at,
                                            )}
                                        />

                                        <InfoStat
                                            label="Причина закриття"
                                            value={
                                                selectedTrade.close_reason
                                                || "—"
                                            }
                                        />
                                    </Box>

                                    <Box
                                        sx={{
                                            display: "grid",
                                            gap: 2,
                                            gridTemplateColumns: {
                                                xs: "1fr",
                                                sm: "repeat(2, minmax(0, 1fr))",
                                                md: "repeat(4, minmax(0, 1fr))",
                                            },
                                            mt: 2,
                                        }}
                                    >
                                        <InfoStat
                                            label="R progress"
                                            value={formatTradeRProgress(selectedTrade)}
                                        />

                                        <InfoStat
                                            label="1R distance"
                                            value={formatOneRDistance(selectedTrade)}
                                        />

                                        <InfoStat
                                            label="BE trigger"
                                            value="1.00R"
                                        />

                                        <InfoStat
                                            label="Profit lock"
                                            value="1.50R"
                                        />
                                    </Box>

                                    {safeArray(selectedTrade.reasons).length > 0 && (
                                        <>
                                            <Divider sx={{ my: 2 }} />

                                            <Typography
                                                variant="subtitle1"
                                                fontWeight={700}
                                                sx={{
                                                    mb: 1,
                                                }}
                                            >
                                                Причини сигналу
                                            </Typography>

                                            <Stack spacing={1}>
                                                {safeArray(
                                                    selectedTrade.reasons,
                                                ).map((reason, index) => (
                                                    <Typography
                                                        key={
                                                            `${selectedTrade.id}-reason-${index}`
                                                        }
                                                        variant="body2"
                                                        color="text.secondary"
                                                        sx={{
                                                            wordBreak: "break-word",
                                                        }}
                                                    >
                                                        • {reason}
                                                    </Typography>
                                                ))}
                                            </Stack>
                                        </>
                                    )}

                                    <Box sx={{ mt: 2 }}>
                                        <SetupVisualization
                                            trade={selectedTrade}
                                            setup={selectedSetup}
                                            setupError={selectedSetupError}
                                            setupLoading={false}
                                        />
                                    </Box>
                                </>
                            ) : (
                                <Typography color="text.secondary">
                                    Немає вибраної угоди.
                                </Typography>
                            )}
                        </Box>
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