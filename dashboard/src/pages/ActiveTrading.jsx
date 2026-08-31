import { useMemo, useState } from "react";

import {
    Alert,
    Box,
    Chip,
    Divider,
    Paper,
    Stack,
    Tab,
    Tabs,
    Typography,
} from "@mui/material";

import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/layout/MetricCard";

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

const ACTIVE_TRADES = [];
const COMPLETED_TRADES = [];

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
    const [assetClass, setAssetClass] = useState("all");
    const [tradeView, setTradeView] = useState("active");

    const filteredActive = useMemo(
        () =>
            ACTIVE_TRADES.filter(
                (trade) => assetClass === "all" || trade.assetClassKey === assetClass,
            ),
        [assetClass],
    );

    const filteredCompleted = useMemo(
        () =>
            COMPLETED_TRADES.filter(
                (trade) => assetClass === "all" || trade.assetClassKey === assetClass,
            ),
        [assetClass],
    );

    return (
        <Box sx={{ width: "100%", minWidth: 0 }}>
            <PageHeader
                title="Active Trading"
                subtitle="Окремий paper-trading контур для акцій, ETF, металів та індексів."
            />

            <Alert severity="info" sx={{ mb: 3, borderRadius: 3 }}>
                Тестовий режим. Тут відображатимуться multi-asset угоди окремо від крипти. Реальні брокерські ордери вимкнені.
            </Alert>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        xl: "repeat(4, minmax(0, 1fr))",
                    },
                    gap: 2,
                    mb: 3,
                }}
            >
                <MetricCard label="Режим" value="Paper" caption="Без реальних ордерів" />
                <MetricCard label="Класи активів" value="4" caption="Stocks / ETF / Metals / Indices" />
                <MetricCard label="Активні угоди" value={String(ACTIVE_TRADES.length)} caption="Multi-asset paper trades" />
                <MetricCard label="Завершені" value={String(COMPLETED_TRADES.length)} caption="Для окремої статистики" />
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
                            Угоди цього класу активів будуть потрапляти у спільний Active Trading журнал з окремим фільтром і статистикою.
                        </Typography>
                    </Paper>
                ))}
            </Box>

            <Paper variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
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
                            emptyMessage="Коли multi-asset scanner почне створювати paper trades, відкриті позиції зʼявляться тут."
                        />
                    )}

                    {tradeView === "completed" && (
                        <TradeList
                            trades={filteredCompleted}
                            emptyMessage="Після TP / SL / expiry завершені угоди з акцій, ETF, металів та індексів зʼявляться тут."
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
                            <MetricCard label="Trades" value="0" caption="Завершені paper trades" />
                            <MetricCard label="Win rate" value="—" caption="Після першої вибірки" />
                            <MetricCard label="P&L" value="—" caption="Окремо від crypto" />
                            <MetricCard label="Profit factor" value="—" caption="Після достатньої статистики" />
                        </Box>
                    )}
                </Box>
            </Paper>
        </Box>
    );
}
