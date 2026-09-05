import { useEffect, useMemo, useState } from "react";

import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Divider,
    Paper,
    Stack,
    Tab,
    Tabs,
    Typography,
} from "@mui/material";

import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/layout/MetricCard";
import { getExperiment1State } from "../api/experiment1Api";

const ACCOUNT_TYPES = [
    { key: "spot", label: "Spot" },
    { key: "futures", label: "Futures" },
];

const ASSET_CLASSES = [
    { key: "all", label: "Усі" },
    { key: "stocks", label: "Акції" },
    { key: "etf", label: "ETF" },
    { key: "metals", label: "Метали" },
    { key: "indices", label: "Індекси" },
];

const MARKET_CARDS = [
    {
        key: "stocks",
        name: "US Stocks",
        detail: "Ліквідні акції США",
        state: "Paper",
    },
    {
        key: "etf",
        name: "ETF",
        detail: "Ліквідні ETF для активної спекуляції",
        state: "Paper",
    },
    {
        key: "metals",
        name: "Gold & Metals",
        detail: "Золото та інші доступні метали",
        state: "Paper",
    },
    {
        key: "indices",
        name: "US Indices",
        detail: "Основні індексні інструменти",
        state: "Paper",
    },
];

function usd(value) {
    const n = Number(value ?? 0);
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number.isFinite(n) ? n : 0);
}

function formatUsd(value) {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
    }).format(value);
}

function EmptyTradeState({ message }) {
    return (
        <Paper variant="outlined" sx={{ p: 3, borderRadius: 3 }}>
            <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
                Поки немає угод
            </Typography>
            <Typography variant="body2" color="text.secondary">
                {message}
            </Typography>
        </Paper>
    );
}

function TradeList({ trades, emptyMessage }) {
    if (!trades.length) {
        return <EmptyTradeState message={emptyMessage} />;
    }

    return (
        <Stack spacing={1.5}>
            {trades.map((trade) => (
                <Paper key={trade.id} variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                    <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1.5}
                        sx={{ justifyContent: "space-between" }}
                    >
                        <Box>
                            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                    {trade.symbol}
                                </Typography>
                                <Chip size="small" label={trade.accountType} variant="outlined" />
                                <Chip size="small" label={trade.assetClass} variant="outlined" />
                                <Chip
                                    size="small"
                                    label={trade.direction}
                                    color={trade.direction === "LONG" ? "success" : "error"}
                                    variant="outlined"
                                />
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                                {trade.strategy} · {trade.timeframe}
                            </Typography>
                        </Box>
                        <Box sx={{ textAlign: { xs: "left", sm: "right" } }}>
                            <Typography variant="body2">Entry: {trade.entry}</Typography>
                            <Typography variant="body2">SL: {trade.stopLoss}</Typography>
                            <Typography variant="body2">TP: {trade.takeProfit}</Typography>
                        </Box>
                    </Stack>
                </Paper>
            ))}
        </Stack>
    );
}

export default function ActiveTrading() {
    const [accountType, setAccountType] = useState("spot");
    const [assetClass, setAssetClass] = useState("all");
    const [tradeView, setTradeView] = useState("active");
    const [state, setState] = useState(null);
    const [error, setError] = useState("");

    useEffect(() => {
        let active = true;
        getExperiment1State().then((data) => { if (active) setState(data); }).catch((err) => { if (active) setError(err?.message || "Не вдалося завантажити runtime state"); });
        return () => { active = false; };
    }, []);

    const byAccount = useMemo(() => new Map((state?.accounts || []).map((item) => [item.account, item])), [state]);
    const spot = byAccount.get("SPOT");
    const futures = byAccount.get("FUTURES");
    const ACTIVE_TRADES = useMemo(() => [spot, futures].flatMap((a) => (a?.positions || []).map((p) => ({ id: `${a.account}-${p.symbol}`, symbol: p.symbol, accountType: a.account === "SPOT" ? "Spot" : "Futures", accountTypeKey: a.account === "SPOT" ? "spot" : "futures", assetClass: "Runtime", assetClassKey: "all", direction: Number(p.quantity) >= 0 ? "LONG" : "SHORT", strategy: "Durable runtime position", timeframe: "runtime", entry: usd(p.average_price), stopLoss: "runtime-managed", takeProfit: "runtime-managed" }))), [spot, futures]);
    const COMPLETED_TRADES = [];

    const filteredActive = useMemo(
        () =>
            ACTIVE_TRADES.filter(
                (trade) =>
                    trade.accountTypeKey === accountType &&
                    (assetClass === "all" || trade.assetClassKey === assetClass),
            ),
        [accountType, assetClass],
    );

    const filteredCompleted = useMemo(
        () =>
            COMPLETED_TRADES.filter(
                (trade) =>
                    trade.accountTypeKey === accountType &&
                    (assetClass === "all" || trade.assetClassKey === assetClass),
            ),
        [accountType, assetClass],
    );

    if (!state && !error) return <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}><CircularProgress /></Box>;

    return (
        <Box sx={{ width: "100%", minWidth: 0 }}>
            <PageHeader
                title="Active Trading"
                subtitle="Experiment 1: два незалежні paper-trading рахунки Spot і Futures, окремо від Investments та crypto statistics."
            />

            {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>{error}</Alert>}

            <Alert severity="info" sx={{ mb: 3, borderRadius: 3 }}>
                Simulation only. Spot і Futures мають окремі баланси, P&L, drawdown та статистику. Реальні брокерські ордери вимкнені.
            </Alert>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: "repeat(2, minmax(0, 1fr))",
                    },
                    gap: 2,
                    mb: 3,
                }}
            >
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                    <Stack spacing={1.5}>
                        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>⚡ Spot account</Typography>
                            <Chip label="Paper" size="small" variant="outlined" />
                        </Stack>
                        <Box
                            sx={{
                                display: "grid",
                                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                                gap: 1.5,
                            }}
                        >
                            <MetricCard label="Equity" value={usd(spot?.last_equity)} caption="Durable runtime state" />
                            <MetricCard label="Realized P&L" value={usd(spot?.realized_pnl)} caption="Окремо від Futures" />
                            <MetricCard label="Max drawdown" value={usd(spot?.max_drawdown)} caption="Runtime ledger" />
                            <MetricCard label="Positions" value={spot?.positions?.length ?? 0} caption="Open paper positions" />
                        </Box>
                    </Stack>
                </Paper>

                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                    <Stack spacing={1.5}>
                        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>🔥 Futures account</Typography>
                            <Chip label="Conservative leverage" size="small" variant="outlined" />
                        </Stack>
                        <Box
                            sx={{
                                display: "grid",
                                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                                gap: 1.5,
                            }}
                        >
                            <MetricCard label="Equity" value={usd(futures?.last_equity)} caption="Durable runtime state" />
                            <MetricCard label="Realized P&L" value={usd(futures?.realized_pnl)} caption="LONG + SHORT" />
                            <MetricCard label="Max drawdown" value={usd(futures?.max_drawdown)} caption="Runtime ledger" />
                            <MetricCard label="Positions" value={futures?.positions?.length ?? 0} caption="Open paper positions" />
                        </Box>
                    </Stack>
                </Paper>
            </Box>

            <Typography variant="h5" sx={{ mb: 2, fontWeight: 700 }}>
                Ринки
            </Typography>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: "repeat(2, minmax(0, 1fr))",
                        xl: "repeat(4, minmax(0, 1fr))",
                    },
                    gap: 2,
                    mb: 4,
                }}
            >
                {MARKET_CARDS.map((market) => (
                    <Paper key={market.key} variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                        <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", mb: 1.5 }}>
                            <Box>
                                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                    {market.name}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {market.detail}
                                </Typography>
                            </Box>
                            <Chip label={market.state} size="small" variant="outlined" />
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                            Угоди цього класу активів потраплятимуть у журнал відповідного Spot або Futures account.
                        </Typography>
                    </Paper>
                ))}
            </Box>

            <Paper variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
                <Box sx={{ px: 2, pt: 1.5 }}>
                    <Tabs value={accountType} onChange={(_, value) => setAccountType(value)}>
                        {ACCOUNT_TYPES.map((item) => (
                            <Tab key={item.key} value={item.key} label={item.label} />
                        ))}
                    </Tabs>
                </Box>

                <Divider />

                <Box sx={{ px: 2, pt: 1.5 }}>
                    <Tabs
                        value={assetClass}
                        onChange={(_, value) => setAssetClass(value)}
                        variant="scrollable"
                        scrollButtons="auto"
                    >
                        {ASSET_CLASSES.map((item) => (
                            <Tab key={item.key} value={item.key} label={item.label} />
                        ))}
                    </Tabs>
                </Box>

                <Divider />

                <Box sx={{ px: 2, pt: 1 }}>
                    <Tabs value={tradeView} onChange={(_, value) => setTradeView(value)}>
                        <Tab value="active" label="Активні угоди" />
                        <Tab value="completed" label="Завершені" />
                        <Tab value="stats" label="Статистика" />
                    </Tabs>
                </Box>

                <Divider />

                <Box sx={{ p: 2 }}>
                    {tradeView === "active" && (
                        <TradeList
                            trades={filteredActive}
                            emptyMessage={`Коли ${accountType === "spot" ? "Spot" : "Futures"} scanner створить paper trades, відкриті позиції зʼявляться тут.`}
                        />
                    )}

                    {tradeView === "completed" && (
                        <TradeList
                            trades={filteredCompleted}
                            emptyMessage={`Завершені ${accountType === "spot" ? "Spot" : "Futures"} угоди зʼявляться тут після exit.`}
                        />
                    )}

                    {tradeView === "stats" && (
                        <Box
                            sx={{
                                display: "grid",
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    sm: "repeat(2, minmax(0, 1fr))",
                                    lg: "repeat(4, minmax(0, 1fr))",
                                },
                                gap: 2,
                            }}
                        >
                            <MetricCard label="Return" value="—" caption={`${accountType === "spot" ? "Spot" : "Futures"} only`} />
                            <MetricCard label="Max drawdown" value="—" caption="Після першої вибірки" />
                            <MetricCard label="Expectancy" value="—" caption="Після завершених угод" />
                            <MetricCard label="Profit factor" value="—" caption="Після достатньої статистики" />
                        </Box>
                    )}
                </Box>
            </Paper>
        </Box>
    );
}
