import { useEffect, useState } from "react";

import {
    Alert,
    Box,
    Button,
    CircularProgress,
    Grid,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { extractApiError } from "../api/researchApi";
import {
    listBacktests,
    runBacktest,
    runStrategyBacktest,
} from "../api/backtestApi";
import PageHeader from "../components/layout/PageHeader";

const SAMPLE_PROFITS = "120,-60,180,-80,90,140,-70,210,-50,160";

function Metric({ label, value }) {
    return (
        <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{value}</Typography>
        </Paper>
    );
}

export default function Backtests() {
    const [running, setRunning] = useState(false);
    const [error, setError] = useState("");
    const [label, setLabel] = useState("Manual historical P&L");
    const [balance, setBalance] = useState("10000");
    const [profits, setProfits] = useState(SAMPLE_PROFITS);
    const [symbol, setSymbol] = useState("BTCUSDT");
    const [timeframe, setTimeframe] = useState("1h");
    const [candleLimit, setCandleLimit] = useState("500");
    const [results, setResults] = useState([]);

    async function refresh() {
        try {
            setResults(await listBacktests());
        } catch (loadError) {
            setError(extractApiError(loadError));
        }
    }

    useEffect(() => { refresh(); }, []);

    async function handleStrategyRun() {
        try {
            setRunning(true);
            setError("");
            await runStrategyBacktest({
                symbol: symbol.trim().toUpperCase(),
                market: "futures",
                timeframe: timeframe.trim(),
                candle_limit: Number(candleLimit),
                initial_balance: Number(balance),
            });
            await refresh();
        } catch (runError) {
            setError(extractApiError(runError));
        } finally {
            setRunning(false);
        }
    }

    async function handleManualRun() {
        try {
            setRunning(true);
            setError("");
            const parsed = profits.split(",").map((value) => Number(value.trim()));
            if (!parsed.length || parsed.some((value) => !Number.isFinite(value))) {
                throw new Error("P&L має бути списком чисел через кому.");
            }
            await runBacktest({
                label,
                initial_balance: Number(balance),
                profits: parsed,
            });
            await refresh();
        } catch (runError) {
            setError(runError?.message || extractApiError(runError));
        } finally {
            setRunning(false);
        }
    }

    const latest = results[0]?.result;

    return (
        <Box sx={{ width: "100%", maxWidth: "100%", minWidth: 0 }}>
            <PageHeader
                title="Backtests"
                subtitle="Історичні тести стратегій з реальними candles та збереженням результатів."
            />

            {error && <Alert severity="warning" sx={{ mb: 3 }}>{error}</Alert>}

            <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 4, mb: 3 }}>
                <Stack spacing={2}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>Breakout на Binance candles</Typography>
                    <Alert severity="info">
                        v2 тестує наявну Breakout strategy. Вхід на відкритті наступної свічки,
                        stop = 1 ATR, target = 2 ATR, quantity = 1. Це research-модель, не live execution.
                    </Alert>
                    <TextField label="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
                    <TextField label="Timeframe" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} helperText="Наприклад: 1h, 4h, 1d" />
                    <TextField label="Candles" type="number" value={candleLimit} onChange={(e) => setCandleLimit(e.target.value)} inputProps={{ min: 220, max: 1000 }} />
                    <TextField label="Початковий баланс" type="number" value={balance} onChange={(e) => setBalance(e.target.value)} />
                    <Button
                        variant="contained"
                        startIcon={running ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />}
                        onClick={handleStrategyRun}
                        disabled={running}
                        sx={{ alignSelf: "flex-start" }}
                    >
                        Запустити Breakout backtest
                    </Button>
                </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 4, mb: 3 }}>
                <Stack spacing={2}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>Ручний P&L тест</Typography>
                    <TextField label="Назва" value={label} onChange={(e) => setLabel(e.target.value)} />
                    <TextField
                        label="P&L кожної історичної угоди, через кому"
                        multiline
                        minRows={3}
                        value={profits}
                        onChange={(e) => setProfits(e.target.value)}
                    />
                    <Button
                        variant="outlined"
                        startIcon={running ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />}
                        onClick={handleManualRun}
                        disabled={running}
                        sx={{ alignSelf: "flex-start" }}
                    >
                        Запустити ручний тест
                    </Button>
                </Stack>
            </Paper>

            {latest && (
                <Grid container spacing={2} sx={{ mb: 3 }}>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Return" value={`${latest.total_return.toFixed(2)}%`} /></Grid>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Trades" value={latest.trades} /></Grid>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Win rate" value={`${latest.win_rate.toFixed(1)}%`} /></Grid>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Max drawdown" value={`${latest.max_drawdown.toFixed(2)}%`} /></Grid>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Profit factor" value={Number.isFinite(latest.profit_factor) ? latest.profit_factor.toFixed(2) : "∞"} /></Grid>
                    <Grid size={{ xs: 6, md: 3 }}><Metric label="Final balance" value={latest.final_balance.toFixed(2)} /></Grid>
                </Grid>
            )}

            <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Історія запусків</Typography>
            <Stack spacing={1.5}>
                {results.length === 0 && <Alert severity="info">Ще немає backtest-запусків.</Alert>}
                {results.map((item) => (
                    <Paper key={item.id} variant="outlined" sx={{ p: 2 }}>
                        <Typography sx={{ fontWeight: 700 }}>{item.label}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {new Date(item.created_at).toLocaleString()} · {item.result.trades} trades · return {item.result.total_return.toFixed(2)}% · win rate {item.result.win_rate.toFixed(1)}%
                        </Typography>
                    </Paper>
                ))}
            </Stack>
        </Box>
    );
}
