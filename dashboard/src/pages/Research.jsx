import {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

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
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";

import {
    extractApiError,
    getLatestScan,
    getResearchStatistics,
    getResearchSetupReasonStatistics,
    getResearchTrades,
    getScanSignals,
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


function normalizeSignalStatus(value) {
    const normalized = String(value || "").trim().toLowerCase();

    if (normalized === "accepted_research") {
        return "research";
    }

    if (normalized === "accepted_elite") {
        return "elite";
    }

    if (
        normalized === "rejected"
        || normalized === "research"
        || normalized === "elite"
        || normalized === "candidate"
        || normalized === "accepted"
    ) {
        return normalized;
    }

    return "candidate";
}


function signalStatusLabel(value) {
    switch (normalizeSignalStatus(value)) {
        case "rejected":
            return "Відхилено";
        case "research":
            return "Research";
        case "elite":
            return "Elite";
        case "accepted":
            return "Прийнято";
        case "candidate":
        default:
            return "Кандидат";
    }
}


function signalStatusColor(value) {
    switch (normalizeSignalStatus(value)) {
        case "rejected":
            return "default";
        case "research":
            return "info";
        case "elite":
            return "success";
        case "accepted":
            return "primary";
        case "candidate":
        default:
            return "warning";
    }
}


function normalizeDirection(value) {
    return String(value || "LONG").trim().toUpperCase();
}


function directionColor(value) {
    return normalizeDirection(value) === "SHORT"
        ? "error"
        : "success";
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

function parseMetadata(value) {
    if (!value) {
        return {};
    }

    if (
        typeof value === "object"
        && !Array.isArray(value)
    ) {
        return value;
    }

    if (typeof value !== "string") {
        return {};
    }

    try {
        const parsed = JSON.parse(value);

        if (
            parsed
            && typeof parsed === "object"
            && !Array.isArray(parsed)
        ) {
            return parsed;
        }
    } catch {
        return {};
    }

    return {};
}


function normalizeConflictInfo(metadata) {
    const source = parseMetadata(metadata);

    if (!source?.direction_conflict) {
        return {
            active: false,
            outcome: "",
            resolution: "",
            winnerDirection: "",
            longScore: null,
            shortScore: null,
            scoreDelta: null,
            minScoreDelta: null,
            longSignalCount: null,
            shortSignalCount: null,
        };
    }

    return {
        active: true,
        outcome: String(
            source.conflict_signal_outcome || "",
        ),
        resolution: String(
            source.conflict_resolution || "",
        ),
        winnerDirection: String(
            source.conflict_winner_direction || "",
        ),
        longScore: source.conflict_long_score ?? null,
        shortScore: source.conflict_short_score ?? null,
        scoreDelta: source.conflict_score_delta ?? null,
        minScoreDelta: source.conflict_min_score_delta ?? null,
        longSignalCount: source.conflict_long_signal_count ?? null,
        shortSignalCount: source.conflict_short_signal_count ?? null,
    };
}


function conflictOutcomeLabel(value) {
    switch (String(value || "")) {
        case "winner":
            return "Переможець напряму";
        case "loser_rejected":
            return "Слабший напрям";
        case "mixed_rejected":
            return "Змішаний конфлікт";
        default:
            return "Conflict resolver";
    }
}


function conflictResolutionLabel(value) {
    switch (String(value || "")) {
        case "winner_selected":
            return "Обрано сильніший напрям";
        case "loser_rejected":
            return "Слабший напрям відхилено";
        case "mixed_rejected":
            return "LONG і SHORT рівні — setup пропущено";
        default:
            return "Конфлікт напрямів";
    }
}


function conflictOutcomeColor(value) {
    switch (String(value || "")) {
        case "winner":
            return "success";
        case "loser_rejected":
            return "error";
        case "mixed_rejected":
            return "warning";
        default:
            return "info";
    }
}


function rejectionCategory(value) {
    const reason = String(value || "").toLowerCase();

    if (!reason) {
        return "";
    }

    if (reason.includes("direction conflict")) {
        return "conflict";
    }

    if (
        reason.includes("probability")
        && reason.includes("below research")
    ) {
        return "research_threshold";
    }

    if (
        reason.includes("probability")
        && reason.includes("below elite")
    ) {
        return "elite_threshold";
    }

    if (reason.includes("research cycle limit")) {
        return "cycle_limit";
    }

    if (reason.includes("open trade already exists")) {
        return "open_trade";
    }

    if (
        reason.includes("duplicate")
        || reason.includes("already tracked")
    ) {
        return "duplicate";
    }

    if (reason.includes("risk")) {
        return "risk";
    }

    return "other";
}


function rejectionCategoryLabel(value) {
    switch (String(value || "")) {
        case "conflict":
            return "Direction conflict";
        case "research_threshold":
            return "Research threshold";
        case "elite_threshold":
            return "Elite threshold";
        case "open_trade":
            return "Open trade exists";
        case "cycle_limit":
            return "Cycle limit";
        case "risk":
            return "Risk error";
        case "duplicate":
            return "Duplicate";
        case "other":
            return "Other rejected";
        default:
            return "";
    }
}


function rejectionCategoryColor(value) {
    switch (String(value || "")) {
        case "conflict":
            return "warning";
        case "research_threshold":
            return "default";
        case "elite_threshold":
            return "info";
        case "open_trade":
            return "primary";
        case "cycle_limit":
            return "secondary";
        case "risk":
            return "error";
        case "duplicate":
            return "primary";
        case "other":
            return "default";
        default:
            return "default";
    }
}



function buildGroupKey(item) {
    return [
        item.symbol,
        item.direction,
        item.timeframe,
        normalizeNumberKey(item.entry),
        normalizeNumberKey(item.stopLoss),
        normalizeNumberKey(item.takeProfit),
        normalizeNumberKey(item.rr),
    ].join("|");
}


function normalizeJournalEntry(raw, index = 0) {
    const metadata = parseMetadata(
        raw?.metadata || raw?.signal?.metadata || {},
    );

    const risk = raw?.risk || metadata?.risk || {};

    const entry = (
        raw?.entry
        ?? raw?.entry_price
        ?? risk?.entry
        ?? metadata?.entry
        ?? null
    );

    const stopLoss = (
        raw?.stop_loss
        ?? raw?.sl
        ?? risk?.stop_loss
        ?? metadata?.stop_loss
        ?? null
    );

    const takeProfit = (
        raw?.take_profit
        ?? raw?.tp
        ?? risk?.take_profit
        ?? metadata?.take_profit
        ?? null
    );

    const rr = (
        raw?.rr
        ?? raw?.risk_reward
        ?? risk?.risk_reward
        ?? metadata?.risk_reward
        ?? null
    );

    const reason = (
        raw?.research_skipped
        || raw?.rejected_reason
        || raw?.reason
        || raw?.message
        || raw?.decision_reason
        || ""
    );

    const conflict = normalizeConflictInfo(metadata);
    const rejectCategory = rejectionCategory(reason);

    return {
        id: raw?.id || raw?.signal_id || `${raw?.symbol || "signal"}-${index}`,
        symbol: raw?.symbol || raw?.signal?.symbol || "—",
        strategy: raw?.strategy || raw?.signal?.strategy || "—",
        direction: normalizeDirection(
            raw?.direction || raw?.signal?.direction,
        ),
        timeframe: raw?.timeframe || raw?.signal?.timeframe || "—",
        probability: raw?.probability ?? metadata?.probability ?? null,
        score: raw?.score ?? raw?.signal?.score ?? null,
        entry,
        stopLoss,
        takeProfit,
        rr,
        reason,
        metadata,
        conflict,
        rejectCategory,
        researchQualified: Number(raw?.probability ?? metadata?.probability ?? 0) >= 40,
        researchBlocked: (
            Number(raw?.probability ?? metadata?.probability ?? 0) >= 40
            && (
                rejectCategory === "open_trade"
                || rejectCategory === "cycle_limit"
                || rejectCategory === "duplicate"
            )
        ),
        status: normalizeSignalStatus(
            raw?.status
            ?? raw?.signal_status
            ?? raw?.journal_status,
        ),
        createdAt: (
            raw?.created_at
            || raw?.started_at
            || raw?.timestamp
            || null
        ),
    };
}

function getLatestScanRun(data) {
    return (
        data?.scan_run
        || data?.latest_scan
        || data?.run
        || null
    );
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


function ScanGroupCard({
    item,
}) {
    const conflictItems = safeArray(item.conflictItems);
    const rejectCategories = safeArray(item.rejectCategories);
    const firstConflict = conflictItems[0] || null;

    return (
        <Paper
            variant="outlined"
            sx={{
                p: 2,
                borderRadius: 3,
                minWidth: 0,
                overflow: "hidden",
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
                spacing={1.5}
                sx={{
                    mb: 1.5,
                }}
            >
                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    flexWrap="wrap"
                    alignItems="center"
                >
                    <Typography
                        variant="h6"
                        fontWeight={700}
                        sx={{
                            wordBreak: "break-word",
                        }}
                    >
                        {item.symbol}
                    </Typography>

                    <Chip
                        size="small"
                        color={directionColor(item.direction)}
                        label={item.direction}
                    />

                    <Chip
                        size="small"
                        color={signalStatusColor(item.status)}
                        label={signalStatusLabel(item.status)}
                    />

                    {firstConflict && (
                        <Chip
                            size="small"
                            color={conflictOutcomeColor(
                                firstConflict.outcome,
                            )}
                            label={conflictOutcomeLabel(
                                firstConflict.outcome,
                            )}
                        />
                    )}

                    {item.researchQualified && (
                        <Chip
                            size="small"
                            color={item.researchBlocked ? "info" : "success"}
                            variant={item.researchBlocked ? "outlined" : "filled"}
                            label={
                                item.researchBlocked
                                    ? "Research blocked"
                                    : "Research-qualified"
                            }
                        />
                    )}

                    {item.duplicates > 1 && (
                        <Chip
                            size="small"
                            variant="outlined"
                            label={`${item.duplicates} дублікати`}
                        />
                    )}

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        {item.timeframe}
                    </Typography>
                </Stack>

                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    flexWrap="wrap"
                >
                    {item.strategies.map((strategy) => (
                        <Chip
                            key={`${item.key}-${strategy}`}
                            size="small"
                            variant="outlined"
                            label={strategy}
                        />
                    ))}
                </Stack>
            </Stack>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        md: "repeat(6, minmax(0, 1fr))",
                    },
                }}
            >
                <InfoStat
                    label="Probability"
                    value={
                        item.probability !== null
                            ? `${formatNumber(item.probability, 0)}%`
                            : "—"
                    }
                />

                <InfoStat
                    label="Score"
                    value={formatNumber(item.score, 0)}
                />

                <InfoStat
                    label="Entry"
                    value={formatPrice(item.entry)}
                />

                <InfoStat
                    label="SL"
                    value={formatPrice(item.stopLoss)}
                />

                <InfoStat
                    label="TP"
                    value={formatPrice(item.takeProfit)}
                />

                <InfoStat
                    label="RR"
                    value={formatNumber(item.rr, 2)}
                />
            </Box>

            {conflictItems.length > 0 && (
                <Paper
                    variant="outlined"
                    sx={{
                        mt: 1.5,
                        p: 1.5,
                        borderRadius: 2,
                        bgcolor: "rgba(255,255,255,0.02)",
                    }}
                >
                    <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        flexWrap="wrap"
                        alignItems="center"
                        sx={{
                            mb: 1,
                        }}
                    >
                        <Typography
                            variant="subtitle2"
                            fontWeight={700}
                        >
                            Conflict resolver
                        </Typography>

                        {firstConflict && (
                            <Chip
                                size="small"
                                color={conflictOutcomeColor(
                                    firstConflict.outcome,
                                )}
                                label={conflictResolutionLabel(
                                    firstConflict.resolution,
                                )}
                            />
                        )}

                        {firstConflict?.winnerDirection && (
                            <Chip
                                size="small"
                                variant="outlined"
                                label={`Winner: ${firstConflict.winnerDirection}`}
                            />
                        )}
                    </Stack>

                    {firstConflict && (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "repeat(2, minmax(0, 1fr))",
                                    md: "repeat(4, minmax(0, 1fr))",
                                },
                            }}
                        >
                            <InfoStat
                                label="LONG score"
                                value={formatNumber(
                                    firstConflict.longScore,
                                    1,
                                )}
                            />

                            <InfoStat
                                label="SHORT score"
                                value={formatNumber(
                                    firstConflict.shortScore,
                                    1,
                                )}
                            />

                            <InfoStat
                                label="Delta"
                                value={formatNumber(
                                    firstConflict.scoreDelta,
                                    1,
                                )}
                            />

                            <InfoStat
                                label="Min delta"
                                value={formatNumber(
                                    firstConflict.minScoreDelta,
                                    1,
                                )}
                            />
                        </Box>
                    )}

                    <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        flexWrap="wrap"
                        sx={{
                            mt: 1,
                        }}
                    >
                        {conflictItems.map((conflict, index) => (
                            <Chip
                                key={`${item.key}-conflict-${index}`}
                                size="small"
                                variant="outlined"
                                color={conflictOutcomeColor(
                                    conflict.outcome,
                                )}
                                label={`${conflictOutcomeLabel(conflict.outcome)}: ${item.items[index]?.strategy || "signal"}`}
                            />
                        ))}
                    </Stack>
                </Paper>
            )}

            {rejectCategories.length > 0 && (
                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    flexWrap="wrap"
                    sx={{
                        mt: 1.5,
                    }}
                >
                    {rejectCategories.map((category) => (
                        <Chip
                            key={`${item.key}-reject-${category}`}
                            size="small"
                            variant="outlined"
                            color={rejectionCategoryColor(category)}
                            label={rejectionCategoryLabel(category)}
                        />
                    ))}
                </Stack>
            )}

            {item.reason && (
                <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                        mt: 1.5,
                        wordBreak: "break-word",
                    }}
                >
                    {item.reason}
                </Typography>
            )}
        </Paper>
    );
}

function TradeCard({
    trade,
    onOpen,
}) {
    return (
        <Paper
            variant="outlined"
            sx={{
                p: 2,
                borderRadius: 3,
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
                spacing={2}
            >
                <Box
                    sx={{
                        minWidth: 0,
                        flex: 1,
                    }}
                >
                    <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        flexWrap="wrap"
                        alignItems="center"
                        sx={{
                            mb: 1.25,
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
                            gap: 2,
                            gridTemplateColumns: {
                                xs: "repeat(2, minmax(0, 1fr))",
                                md: "repeat(6, minmax(0, 1fr))",
                            },
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
                            value={formatNumber(trade.rr, 2)}
                        />

                        <InfoStat
                            label="PnL"
                            value={`${formatNumber(trade.profit_amount, 2)} USDT`}
                        />
                    </Box>
                </Box>

                <Button
                    variant="outlined"
                    startIcon={<VisibilityOutlinedIcon />}
                    onClick={() => onOpen(trade)}
                    sx={{
                        alignSelf: {
                            xs: "stretch",
                            lg: "center",
                        },
                        minWidth: 150,
                    }}
                >
                    Відкрити
                </Button>
            </Stack>
        </Paper>
    );
}



function compactObjectStats(value) {
    if (
        !value
        || typeof value !== "object"
        || Array.isArray(value)
    ) {
        return "—";
    }

    const entries = Object
        .entries(value)
        .sort((left, right) => Number(right[1]) - Number(left[1]))
        .slice(0, 4);

    if (!entries.length) {
        return "—";
    }

    return entries
        .map(([key, count]) => `${key}: ${count}`)
        .join(" · ");
}


function StatsReasonRows({
    title,
    rows,
    mode = "performance",
}) {
    const items = safeArray(rows).slice(0, 8);

    return (
        <Box sx={{ minWidth: 0 }}>
            <Typography
                variant="h6"
                fontWeight={700}
                sx={{ mb: 1.5 }}
            >
                {title}
            </Typography>

            {items.length === 0 ? (
                <Typography
                    variant="body2"
                    color="text.secondary"
                >
                    No data yet.
                </Typography>
            ) : (
                <Stack spacing={1.25}>
                    {items.map((row, index) => (
                        <Paper
                            key={`${title}-${row.label || index}`}
                            variant="outlined"
                            sx={{
                                p: 1.5,
                                borderRadius: 2,
                                bgcolor: "rgba(255,255,255,0.02)",
                                minWidth: 0,
                            }}
                        >
                            <Stack
                                direction="row"
                                spacing={1}
                                useFlexGap
                                flexWrap="wrap"
                                alignItems="center"
                                sx={{ mb: 1 }}
                            >
                                <Typography
                                    variant="subtitle2"
                                    fontWeight={700}
                                    sx={{
                                        wordBreak: "break-word",
                                    }}
                                >
                                    {row.label || "Unknown"}
                                </Typography>

                                <Chip
                                    size="small"
                                    variant="outlined"
                                    label={
                                        mode === "blocks"
                                            ? `Count: ${formatNumber(row.count, 0)}`
                                            : `Total: ${formatNumber(row.total, 0)}`
                                    }
                                />
                            </Stack>

                            {mode === "blocks" ? (
                                <Box
                                    sx={{
                                        display: "grid",
                                        gap: 1.5,
                                        gridTemplateColumns: {
                                            xs: "1fr",
                                            md: "repeat(2, minmax(0, 1fr))",
                                        },
                                    }}
                                >
                                    <InfoStat
                                        label="Strategies"
                                        value={compactObjectStats(row.strategies)}
                                    />

                                    <InfoStat
                                        label="Directions"
                                        value={compactObjectStats(row.directions)}
                                    />
                                </Box>
                            ) : (
                                <Box
                                    sx={{
                                        display: "grid",
                                        gap: 1.5,
                                        gridTemplateColumns: {
                                            xs: "repeat(2, minmax(0, 1fr))",
                                            md: "repeat(4, minmax(0, 1fr))",
                                        },
                                    }}
                                >
                                    <InfoStat
                                        label="Completed"
                                        value={formatNumber(row.completed, 0)}
                                    />

                                    <InfoStat
                                        label="W/L"
                                        value={`${formatNumber(row.wins, 0)} / ${formatNumber(row.losses, 0)}`}
                                    />

                                    <InfoStat
                                        label="Win rate"
                                        value={`${formatNumber(row.win_rate, 2)}%`}
                                    />

                                    <InfoStat
                                        label="Avg RR"
                                        value={formatNumber(row.average_rr, 2)}
                                    />
                                </Box>
                            )}

                            {mode === "blocks" && safeArray(row.examples).length > 0 && (
                                <Typography
                                    variant="body2"
                                    color="text.secondary"
                                    sx={{
                                        mt: 1,
                                        wordBreak: "break-word",
                                    }}
                                >
                                    {safeArray(row.examples)[0]}
                                </Typography>
                            )}
                        </Paper>
                    ))}
                </Stack>
            )}
        </Box>
    );
}


function SetupReasonStatisticsPanel({
    setupReasonStats,
}) {
    if (!setupReasonStats) {
        return null;
    }

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
                    md: "row",
                }}
                justifyContent="space-between"
                alignItems={{
                    xs: "flex-start",
                    md: "center",
                }}
                spacing={1.5}
                sx={{ mb: 2 }}
            >
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="h4"
                        fontWeight={700}
                    >
                        Setup Reason Statistics
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mt: 0.75 }}
                    >
                        Performance by setup reason and blocked signal reasons.
                    </Typography>
                </Box>
            </Stack>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        xl: "repeat(2, minmax(0, 1fr))",
                    },
                }}
            >
                <StatsReasonRows
                    title="Setup reasons"
                    rows={setupReasonStats.by_setup_reason}
                />

                <StatsReasonRows
                    title="Block reasons"
                    rows={setupReasonStats.signal_block_reasons}
                    mode="blocks"
                />

                <StatsReasonRows
                    title="Strategies"
                    rows={setupReasonStats.by_strategy}
                />

                <StatsReasonRows
                    title="Close reasons"
                    rows={setupReasonStats.by_close_reason}
                />
            </Box>
        </Paper>
    );
}


export default function Research() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const [statistics, setStatistics] = useState(null);
    const [setupReasonStats, setSetupReasonStats] = useState(null);
    const [workerStatus, setWorkerStatus] = useState(null);
    const [trades, setTrades] = useState([]);

    const [latestScanRun, setLatestScanRun] = useState(null);
    const [latestScanEntries, setLatestScanEntries] = useState([]);
    const [latestScanEntriesTotal, setLatestScanEntriesTotal] = useState(0);

    const [scanStatusFilter, setScanStatusFilter] = useState("all");
    const [scanDirectionFilter, setScanDirectionFilter] = useState("all");
    const [scanRejectionFilter, setScanRejectionFilter] = useState("all");
    const [scanConflictFilter, setScanConflictFilter] = useState("all");
    const [scanResearchFilter, setScanResearchFilter] = useState("all");

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
                setupReasonStatsData,
                workerStatusData,
                tradesData,
                latestScanData,
            ] = await Promise.all([
                getResearchStatistics(),
                getResearchSetupReasonStatistics(),
                getWorkerStatus(),
                getResearchTrades({
                    limit: 100,
                }),
                getLatestScan(),
            ]);

            setStatistics(statisticsData || null);
            setSetupReasonStats(setupReasonStatsData || null);
            setWorkerStatus(workerStatusData || null);
            setTrades(safeArray(tradesData?.trades));

            const scanRun = getLatestScanRun(latestScanData);

            setLatestScanRun(scanRun);

            if (!scanRun?.id) {
                setLatestScanEntries([]);
                setLatestScanEntriesTotal(0);
                return;
            }

            const signalsData = await getScanSignals(
                scanRun.id,
                {
                    status: scanStatusFilter === "all"
                        ? ""
                        : scanStatusFilter,
                    limit: 200,
                },
            );

            setLatestScanEntries(
                safeArray(signalsData?.signals),
            );

            setLatestScanEntriesTotal(
                Number(signalsData?.total ?? 0),
            );
        },
        [
            scanStatusFilter,
        ],
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

    const normalizedScanEntries = useMemo(
        () => latestScanEntries.map(
            (item, index) => normalizeJournalEntry(
                item,
                index,
            ),
        ),
        [
            latestScanEntries,
        ],
    );

    const groupedScanEntries = useMemo(
        () => {
            const groups = new Map();

            normalizedScanEntries.forEach((item) => {
                const key = buildGroupKey(item);

                if (!groups.has(key)) {
                    groups.set(
                        key,
                        {
                            key,
                            symbol: item.symbol,
                            direction: item.direction,
                            timeframe: item.timeframe,
                            probability: item.probability,
                            score: item.score,
                            entry: item.entry,
                            stopLoss: item.stopLoss,
                            takeProfit: item.takeProfit,
                            rr: item.rr,
                            status: item.status,
                            reason: item.reason,
                            createdAt: item.createdAt,
                            strategies: [],
                            duplicates: 0,
                            items: [],
                            conflictItems: [],
                            rejectCategories: [],
                            researchQualified: false,
                            researchBlocked: false,
                        },
                    );
                }

                const group = groups.get(key);

                group.items.push(item);
                group.duplicates += 1;

                if (
                    item.strategy
                    && !group.strategies.includes(item.strategy)
                ) {
                    group.strategies.push(item.strategy);
                }

                if (!group.reason && item.reason) {
                    group.reason = item.reason;
                }

                if (item.conflict?.active) {
                    group.conflictItems.push(
                        item.conflict,
                    );
                }

                if (
                    item.rejectCategory
                    && !group.rejectCategories.includes(item.rejectCategory)
                ) {
                    group.rejectCategories.push(
                        item.rejectCategory,
                    );
                }

                if (item.researchQualified) {
                    group.researchQualified = true;
                }

                if (item.researchBlocked) {
                    group.researchBlocked = true;
                }

                if (
                    group.status !== "elite"
                    && item.status === "elite"
                ) {
                    group.status = "elite";
                } else if (
                    group.status === "candidate"
                    && item.status !== "candidate"
                ) {
                    group.status = item.status;
                }
            });

            return Array
                .from(groups.values())
                .sort((left, right) => {
                    const leftTime = left.createdAt
                        ? new Date(left.createdAt).getTime()
                        : 0;

                    const rightTime = right.createdAt
                        ? new Date(right.createdAt).getTime()
                        : 0;

                    return rightTime - leftTime;
                });
        },
        [
            normalizedScanEntries,
        ],
    );

    const filteredGroupedSignals = useMemo(
        () => groupedScanEntries.filter((item) => {
            const directionMatches = (
                scanDirectionFilter === "all"
                || item.direction === scanDirectionFilter
            );

            const rejectionMatches = (
                scanRejectionFilter === "all"
                || safeArray(item.rejectCategories).includes(
                    scanRejectionFilter,
                )
            );

            const conflictMatches = (
                scanConflictFilter === "all"
                || safeArray(item.conflictItems).some(
                    (conflict) => conflict?.outcome === scanConflictFilter,
                )
            );

            const researchMatches = (
                scanResearchFilter === "all"
                || (
                    scanResearchFilter === "qualified"
                    && item.researchQualified
                )
                || (
                    scanResearchFilter === "blocked"
                    && item.researchBlocked
                )
            );

            return (
                directionMatches
                && rejectionMatches
                && conflictMatches
                && researchMatches
            );
        }),
        [
            groupedScanEntries,
            scanDirectionFilter,
            scanRejectionFilter,
            scanConflictFilter,
            scanResearchFilter,
        ],
    );

    const scanLongCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.direction === "LONG",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanShortCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.direction === "SHORT",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanConflictCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.conflict?.active,
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanConflictMixedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.conflict?.outcome === "mixed_rejected",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanConflictWinnerCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.conflict?.outcome === "winner",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanConflictLoserCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.conflict?.outcome === "loser_rejected",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanResearchThresholdRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "research_threshold",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanEliteThresholdRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "elite_threshold",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanOpenTradeRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "open_trade",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanCycleLimitRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "cycle_limit",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanRiskRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "risk",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanOtherRejectedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.rejectCategory === "other",
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanResearchQualifiedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.researchQualified,
        ).length,
        [
            normalizedScanEntries,
        ],
    );

    const scanResearchBlockedCount = useMemo(
        () => normalizedScanEntries.filter(
            (item) => item.researchBlocked,
        ).length,
        [
            normalizedScanEntries,
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
                        variant="h6"
                        color="text.secondary"
                        sx={{
                            mt: 1,
                            wordBreak: "break-word",
                        }}
                    >
                        Virtual trades, статистика, журнал
                        сканувань та setup-аналіз.
                    </Typography>
                </Box>

                <Button
                    variant="contained"
                    size="large"
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
                        minWidth: 180,
                        alignSelf: {
                            xs: "stretch",
                            md: "auto",
                        },
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
                    }}
                >
                    {error}
                </Alert>
            )}

            <WorkerStatusPanel
                workerStatus={workerStatus}
                statistics={statistics}
            />

            <SetupReasonStatisticsPanel
                setupReasonStats={setupReasonStats}
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
                    mb: 3,
                    minWidth: 0,
                }}
            >
                <Stack
                    direction="column"
                    justifyContent="flex-start"
                    alignItems="stretch"
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
                            Останнє сканування
                        </Typography>

                        <Typography
                            variant="body1"
                            color="text.secondary"
                            sx={{
                                mt: 1,
                                wordBreak: "break-word",
                            }}
                        >
                            Дублі по одному symbol / direction /
                            entry / SL / TP згруповані в одну картку.
                        </Typography>
                    </Box>

                    <Stack
                        direction={{
                            xs: "column",
                            sm: "row",
                        }}
                        spacing={1.5}
                        useFlexGap
                        flexWrap="wrap"
                        justifyContent="flex-start"
                        sx={{
                            width: "100%",
                            alignItems: {
                                xs: "stretch",
                                sm: "center",
                            },
                        }}
                    >
                        <Chip
                            color={
                                latestScanRun?.status === "completed"
                                    ? "success"
                                    : latestScanRun?.status === "failed"
                                        ? "error"
                                        : "default"
                            }
                            label={latestScanRun?.status || "unknown"}
                            sx={{
                                alignSelf: {
                                    xs: "flex-start",
                                    sm: "center",
                                },
                            }}
                        />

                        <FormControl
                            size="small"
                            sx={{
                                minWidth: {
                                    xs: "100%",
                                    sm: 135,
                                },
                            }}
                        >
                            <Select
                                value={scanStatusFilter}
                                onChange={(event) => {
                                    setScanStatusFilter(
                                        event.target.value,
                                    );
                                }}
                            >
                                <MenuItem value="all">
                                    Сигнали
                                </MenuItem>

                                <MenuItem value="candidate">
                                    Candidate
                                </MenuItem>

                                <MenuItem value="rejected">
                                    Rejected
                                </MenuItem>

                                <MenuItem value="research">
                                    Research
                                </MenuItem>

                                <MenuItem value="elite">
                                    Elite
                                </MenuItem>
                            </Select>
                        </FormControl>

                        <FormControl
                            size="small"
                            sx={{
                                minWidth: {
                                    xs: "100%",
                                    sm: 135,
                                },
                            }}
                        >
                            <Select
                                value={scanDirectionFilter}
                                onChange={(event) => {
                                    setScanDirectionFilter(
                                        event.target.value,
                                    );
                                }}
                            >
                                <MenuItem value="all">
                                    Напрямок
                                </MenuItem>

                                <MenuItem value="LONG">
                                    LONG
                                </MenuItem>

                                <MenuItem value="SHORT">
                                    SHORT
                                </MenuItem>
                            </Select>
                        </FormControl>

                        <FormControl
                            size="small"
                            sx={{
                                minWidth: {
                                    xs: "100%",
                                    sm: 175,
                                },
                            }}
                        >
                            <Select
                                value={scanRejectionFilter}
                                onChange={(event) => {
                                    setScanRejectionFilter(
                                        event.target.value,
                                    );
                                    setScanConflictFilter("all");
                                }}
                            >
                                <MenuItem value="all">
                                    Причина відхилення
                                </MenuItem>

                                <MenuItem value="conflict">
                                    Direction conflict
                                </MenuItem>

                                <MenuItem value="research_threshold">
                                    Research threshold
                                </MenuItem>

                                <MenuItem value="elite_threshold">
                                    Elite threshold
                                </MenuItem>

                                <MenuItem value="open_trade">
                                    Open trade exists
                                </MenuItem>

                                <MenuItem value="cycle_limit">
                                    Cycle limit
                                </MenuItem>

                                <MenuItem value="risk">
                                    Risk error
                                </MenuItem>

                                <MenuItem value="duplicate">
                                    Duplicate
                                </MenuItem>

                                <MenuItem value="other">
                                    Other rejected
                                </MenuItem>
                            </Select>
                        </FormControl>

                        <FormControl
                            size="small"
                            sx={{
                                minWidth: {
                                    xs: "100%",
                                    sm: 165,
                                },
                            }}
                        >
                            <Select
                                value={scanResearchFilter}
                                onChange={(event) => {
                                    setScanResearchFilter(
                                        event.target.value,
                                    );
                                }}
                            >
                                <MenuItem value="all">
                                    Research стан
                                </MenuItem>

                                <MenuItem value="qualified">
                                    Research-qualified
                                </MenuItem>

                                <MenuItem value="blocked">
                                    Research blocked
                                </MenuItem>
                            </Select>
                        </FormControl>

                        <Button
                            variant="outlined"
                            size="small"
                            onClick={() => {
                                setScanStatusFilter("all");
                                setScanDirectionFilter("all");
                                setScanRejectionFilter("all");
                                setScanConflictFilter("all");
                                setScanResearchFilter("all");
                            }}
                            disabled={
                                scanStatusFilter === "all"
                                && scanDirectionFilter === "all"
                                && scanRejectionFilter === "all"
                                && scanConflictFilter === "all"
                                && scanResearchFilter === "all"
                            }
                            sx={{
                                height: 40,
                                minHeight: 40,
                                whiteSpace: "nowrap",
                                fontSize: "0.82rem",
                                alignSelf: {
                                    xs: "stretch",
                                    sm: "center",
                                },
                                minWidth: {
                                    xs: "100%",
                                    sm: 115,
                                },
                            }}
                        >
                            Reset filters
                        </Button>
                    </Stack>
                </Stack>

                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                        gridTemplateColumns: {
                            xs: "1fr",
                            sm: "repeat(2, minmax(0, 1fr))",
                            md: "repeat(3, minmax(0, 1fr))",
                            xl: "repeat(8, minmax(0, 1fr))",
                        },
                        mb: 2,
                    }}
                >
                    <InfoStat
                        label="Початок"
                        value={formatDateTime(latestScanRun?.started_at)}
                    />

                    <InfoStat
                        label="Завершено"
                        value={formatDateTime(latestScanRun?.finished_at)}
                    />

                    <InfoStat
                        label="TF"
                        value={latestScanRun?.timeframe || "—"}
                    />

                    <InfoStat
                        label="Перевірено пар"
                        value={formatNumber(
                            latestScanRun?.symbols_scanned,
                            0,
                        )}
                    />

                    <InfoStat
                        label="Кандидатів"
                        value={formatNumber(
                            latestScanRun?.candidate_signals,
                            0,
                        )}
                    />

                    <InfoStat
                        label="Research trades"
                        value={formatNumber(
                            latestScanRun?.research_trades_created,
                            0,
                        )}
                    />

                    <InfoStat
                        label="Elite signals"
                        value={formatNumber(
                            latestScanRun?.elite_signals_found,
                            0,
                        )}
                    />

                    <InfoStat
                        label="Показано"
                        value={
                            `${filteredGroupedSignals.length}/${groupedScanEntries.length}`
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
                            lg: "repeat(4, minmax(0, 1fr))",
                        },
                        mb: 2,
                    }}
                >
                    <InfoStat
                        label="LONG записів"
                        value={formatNumber(scanLongCount, 0)}
                    />

                    <InfoStat
                        label="SHORT записів"
                        value={formatNumber(scanShortCount, 0)}
                    />

                    <InfoStat
                        label="Статус scan-run"
                        value={latestScanRun?.status || "—"}
                    />

                    <InfoStat
                        label="Записів API"
                        value={
                            `${latestScanEntries.length}/${latestScanEntriesTotal}`
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
                            lg: "repeat(4, minmax(0, 1fr))",
                        },
                        mb: 2,
                    }}
                >
                    <InfoStat
                        label="Conflict записів"
                        value={formatNumber(scanConflictCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("conflict");
                            setScanConflictFilter("all");
                        }}
                        active={
                            scanRejectionFilter === "conflict"
                            && scanConflictFilter === "all"
                        }
                    />

                    <InfoStat
                        label="Winner"
                        value={formatNumber(scanConflictWinnerCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("all");
                            setScanConflictFilter("winner");
                        }}
                        active={scanConflictFilter === "winner"}
                    />

                    <InfoStat
                        label="Loser rejected"
                        value={formatNumber(scanConflictLoserCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("all");
                            setScanConflictFilter("loser_rejected");
                        }}
                        active={scanConflictFilter === "loser_rejected"}
                    />

                    <InfoStat
                        label="Mixed conflict"
                        value={formatNumber(scanConflictMixedCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("all");
                            setScanConflictFilter("mixed_rejected");
                        }}
                        active={scanConflictFilter === "mixed_rejected"}
                    />
                </Box>

                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                        gridTemplateColumns: {
                            xs: "1fr",
                            sm: "repeat(2, minmax(0, 1fr))",
                            lg: "repeat(6, minmax(0, 1fr))",
                        },
                        mb: 2,
                    }}
                >
                    <InfoStat
                        label="Research threshold"
                        value={formatNumber(
                            scanResearchThresholdRejectedCount,
                            0,
                        )}
                        onClick={() => {
                            setScanRejectionFilter("research_threshold");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "research_threshold"}
                    />

                    <InfoStat
                        label="Elite threshold"
                        value={formatNumber(
                            scanEliteThresholdRejectedCount,
                            0,
                        )}
                        onClick={() => {
                            setScanRejectionFilter("elite_threshold");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "elite_threshold"}
                    />

                    <InfoStat
                        label="Open trade exists"
                        value={formatNumber(
                            scanOpenTradeRejectedCount,
                            0,
                        )}
                        onClick={() => {
                            setScanRejectionFilter("open_trade");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "open_trade"}
                    />

                    <InfoStat
                        label="Cycle limit"
                        value={formatNumber(
                            scanCycleLimitRejectedCount,
                            0,
                        )}
                        onClick={() => {
                            setScanRejectionFilter("cycle_limit");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "cycle_limit"}
                    />

                    <InfoStat
                        label="Risk error"
                        value={formatNumber(scanRiskRejectedCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("risk");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "risk"}
                    />

                    <InfoStat
                        label="Other rejected"
                        value={formatNumber(scanOtherRejectedCount, 0)}
                        onClick={() => {
                            setScanRejectionFilter("other");
                            setScanConflictFilter("all");
                        }}
                        active={scanRejectionFilter === "other"}
                    />
                </Box>

                {scanShortCount === 0 && scanLongCount > 0 && (
                    <Alert
                        severity="warning"
                        icon={<WarningAmberRoundedIcon />}
                        sx={{
                            mb: 2,
                        }}
                    >
                        У цьому scan-run немає жодного SHORT.
                        Dashboard їх не ховає — backend scanner зараз
                        повернув тільки LONG-сигнали.
                    </Alert>
                )}

                <Stack spacing={2}>
                    {filteredGroupedSignals.length === 0 ? (
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
                                Немає записів для поточного фільтра.
                            </Typography>
                        </Paper>
                    ) : (
                        filteredGroupedSignals.map((item) => (
                            <ScanGroupCard
                                key={item.key}
                                item={item}
                            />
                        ))
                    )}
                </Stack>
            </Paper>

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
                        label={`Угод: ${trades.length}`}
                    />
                </Stack>

                <Stack spacing={2}>
                    {trades.length === 0 ? (
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
                        trades.map((trade) => (
                            <TradeCard
                                key={trade.id}
                                trade={trade}
                                onOpen={handleOpenTrade}
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
                                            color={directionColor(
                                                selectedTrade.direction,
                                            )}
                                            label={selectedTrade.direction}
                                        />

                                        <Chip
                                            variant="outlined"
                                            label={selectedTrade.strategy}
                                        />
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
                                            value={formatNumber(
                                                selectedTrade.rr,
                                                2,
                                            )}
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