import {
    useCallback,
    useEffect,
    useMemo,
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

import { extractApiError, getResearchTrades } from "../api/researchApi";

import MetricCard from "../components/layout/MetricCard";
import PageHeader from "../components/layout/PageHeader";


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
    return formatNumber(value, 8);
}


function normalizeDirection(value) {
    return String(value || "").trim().toUpperCase();
}


function directionColor(value) {
    return normalizeDirection(value) === "SHORT"
        ? "error"
        : "success";
}


const STATUS_LABELS = {
    active: "Активна",
    waiting_entry: "Очікує входу",
};


function statusLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();

    return STATUS_LABELS[normalized] || value || "—";
}


function statusColor(value) {
    const normalized = String(value || "").trim().toLowerCase();

    return normalized === "active"
        ? "success"
        : "warning";
}


function researchGroupLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();

    return normalized === "experimental"
        ? "Experimental"
        : "Core";
}


function dedupeById(trades) {
    const byId = new Map();

    for (const trade of trades) {
        if (trade && trade.id && !byId.has(trade.id)) {
            byId.set(trade.id, trade);
        }
    }

    return Array.from(byId.values());
}


function sumNotional(trades) {
    return trades.reduce(
        (total, trade) => {
            const numeric = Number(trade?.notional);

            return Number.isFinite(numeric)
                ? total + numeric
                : total;
        },
        0,
    );
}


function normalizeMarket(value) {
    return String(value || "").trim().toLowerCase();
}


function emptySegment() {
    return {
        count: 0,
        notional: 0,
    };
}


function addToSegment(segment, notional) {
    segment.count += 1;
    segment.notional += notional;
}


/**
 * Break open positions down by market (spot/futures) and direction
 * (long/short). null/NaN notional is ignored in the sums (contributes
 * 0) but the trade is still counted - matches the same convention as
 * sumNotional() above. A trade with an unrecognized market or
 * direction simply does not add to that particular segment; it still
 * appears in the main positions table untouched.
 */
function computeExposureBreakdown(trades) {
    const breakdown = {
        spot: emptySegment(),
        futures: emptySegment(),
        long: emptySegment(),
        short: emptySegment(),
    };

    for (const trade of trades) {
        const numeric = Number(trade?.notional);
        const validNotional = Number.isFinite(numeric)
            ? numeric
            : 0;

        const market = normalizeMarket(trade?.market);

        if (market === "spot") {
            addToSegment(breakdown.spot, validNotional);
        } else if (market === "futures") {
            addToSegment(breakdown.futures, validNotional);
        }

        const direction = normalizeDirection(trade?.direction);

        if (direction === "LONG") {
            addToSegment(breakdown.long, validNotional);
        } else if (direction === "SHORT") {
            addToSegment(breakdown.short, validNotional);
        }
    }

    return breakdown;
}


/**
 * Portfolio v1: frontend-only view over currently open Research trades
 * (active + waiting_entry). There is no separate positions table and no
 * real exchange balance anywhere in this codebase (MarketHunter only
 * ever creates virtual/paper ResearchTrade records) - this page is a
 * read-only projection of the existing /research/trades endpoint, not
 * a new data source. portfolio_api.py / GET /portfolio/status is
 * intentionally left untouched.
 */
export default function Portfolio() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [activeTrades, setActiveTrades] = useState([]);
    const [waitingTrades, setWaitingTrades] = useState([]);

    const loadData = useCallback(
        async () => {
            const [activeResult, waitingResult] = await Promise.all([
                getResearchTrades({
                    status: "active",
                    limit: 200,
                }),
                getResearchTrades({
                    status: "waiting_entry",
                    limit: 200,
                }),
            ]);

            setActiveTrades(
                Array.isArray(activeResult?.trades)
                    ? activeResult.trades
                    : [],
            );

            setWaitingTrades(
                Array.isArray(waitingResult?.trades)
                    ? waitingResult.trades
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

    // active_trades and waiting_trades both come back from the API
    // already ordered created_at DESC (newest first). Concatenating
    // active before waiting_entry gives exactly the required order:
    // active trades first, waiting_entry second, newer above older
    // within each group - no extra client-side sort needed.
    const positions = useMemo(
        () => dedupeById([
            ...activeTrades,
            ...waitingTrades,
        ]),
        [
            activeTrades,
            waitingTrades,
        ],
    );

    const totalNotional = useMemo(
        () => sumNotional(positions),
        [positions],
    );

    const exposureBreakdown = useMemo(
        () => computeExposureBreakdown(positions),
        [positions],
    );

    const netBias = (
        exposureBreakdown.long.notional
        - exposureBreakdown.short.notional
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
                title="Portfolio"
                subtitle="Реальні відкриті Research trades (active + waiting_entry). Без вигаданого balance/equity."
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
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                    },
                    mb: 3,
                }}
            >
                <MetricCard
                    label="Open trades"
                    value={positions.length}
                />

                <MetricCard
                    label="Notional exposure"
                    value={formatNumber(totalNotional, 2)}
                />
            </Box>

            <Box sx={{ mb: 3, minWidth: 0 }}>
                <Typography
                    variant="subtitle1"
                    fontWeight={600}
                    sx={{ mb: 1.5 }}
                >
                    Розподіл відкритої експозиції
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
                        mb: 2,
                    }}
                >
                    <MetricCard
                        label="SPOT"
                        value={exposureBreakdown.spot.count}
                        caption={`Notional: ${formatNumber(exposureBreakdown.spot.notional, 2)}`}
                    />

                    <MetricCard
                        label="FUTURES"
                        value={exposureBreakdown.futures.count}
                        caption={`Notional: ${formatNumber(exposureBreakdown.futures.notional, 2)}`}
                    />

                    <MetricCard
                        label="LONG"
                        value={exposureBreakdown.long.count}
                        caption={`Notional: ${formatNumber(exposureBreakdown.long.notional, 2)}`}
                        valueColor="success.main"
                    />

                    <MetricCard
                        label="SHORT"
                        value={exposureBreakdown.short.count}
                        caption={`Notional: ${formatNumber(exposureBreakdown.short.notional, 2)}`}
                        valueColor="error.main"
                    />
                </Box>

                <Paper
                    variant="outlined"
                    sx={{
                        p: 2,
                        borderRadius: 3,
                        bgcolor: "rgba(255,255,255,0.02)",
                        minWidth: 0,
                    }}
                >
                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        Net bias (LONG − SHORT notional)
                    </Typography>

                    <Typography
                        variant="h6"
                        fontWeight={700}
                        color={
                            netBias > 0
                                ? "success.main"
                                : netBias < 0
                                    ? "error.main"
                                    : "text.primary"
                        }
                        sx={{ mt: 0.5, wordBreak: "break-word" }}
                    >
                        {formatNumber(netBias, 2)}
                    </Typography>
                </Paper>
            </Box>

            {positions.length === 0 ? (
                <Paper
                    variant="outlined"
                    sx={{
                        p: 4,
                        borderRadius: 4,
                        textAlign: "center",
                    }}
                >
                    <Typography color="text.secondary">
                        Немає відкритих Research trades (active або waiting_entry).
                    </Typography>
                </Paper>
            ) : (
                <TableContainer
                    component={Paper}
                    variant="outlined"
                    sx={{
                        borderRadius: 4,
                    }}
                >
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Symbol</TableCell>
                                <TableCell>Market</TableCell>
                                <TableCell>Direction</TableCell>
                                <TableCell>Strategy</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell align="right">Entry</TableCell>
                                <TableCell align="right">Stop loss</TableCell>
                                <TableCell align="right">Take profit</TableCell>
                                <TableCell align="right">Notional</TableCell>
                                <TableCell align="right">Candles</TableCell>
                                <TableCell>Group</TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {positions.map((trade) => (
                                <TableRow key={trade.id}>
                                    <TableCell>
                                        {trade.symbol || "—"}
                                    </TableCell>

                                    <TableCell>
                                        {trade.market || "—"}
                                    </TableCell>

                                    <TableCell>
                                        <Chip
                                            size="small"
                                            label={normalizeDirection(trade.direction) || "—"}
                                            color={directionColor(trade.direction)}
                                            variant="outlined"
                                        />
                                    </TableCell>

                                    <TableCell>
                                        {trade.strategy || "—"}
                                    </TableCell>

                                    <TableCell>
                                        <Chip
                                            size="small"
                                            label={statusLabel(trade.status)}
                                            color={statusColor(trade.status)}
                                            variant="outlined"
                                        />
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatPrice(trade.entry_price)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatPrice(trade.stop_loss)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatPrice(trade.take_profit)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {formatNumber(trade.notional, 2)}
                                    </TableCell>

                                    <TableCell align="right">
                                        {trade.active_candles ?? "—"}
                                        {" / "}
                                        {trade.max_active_candles ?? "—"}
                                    </TableCell>

                                    <TableCell>
                                        {researchGroupLabel(trade.research_group)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}
        </Box>
    );
}
