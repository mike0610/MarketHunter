import { useEffect, useMemo, useState } from "react";
import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Paper,
    Stack,
    Typography,
} from "@mui/material";

import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/layout/MetricCard";
import { getExperiment1State } from "../api/experiment1Api";

const MONTHLY_CONTRIBUTION = 2000;

const LEDGERS = [
    { key: "INVESTMENTS_DEFENSIVE", name: "Defensive", risk: "Низький ризик" },
    { key: "INVESTMENTS_BALANCED", name: "Balanced", risk: "Середній ризик" },
    { key: "INVESTMENTS_GROWTH", name: "Growth", risk: "Високий ризик" },
];

function usd(value) {
    const number = Number(value ?? 0);
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(Number.isFinite(number) ? number : 0);
}

export default function Investments() {
    const [state, setState] = useState(null);
    const [error, setError] = useState("");

    useEffect(() => {
        let active = true;
        getExperiment1State()
            .then((data) => {
                if (active) setState(data);
            })
            .catch((err) => {
                if (active) setError(err?.message || "Не вдалося завантажити Experiment1 state");
            });
        return () => { active = false; };
    }, []);

    const accounts = useMemo(() => {
        const byName = new Map((state?.accounts || []).map((item) => [item.account, item]));
        return LEDGERS.map((ledger) => ({ ...ledger, data: byName.get(ledger.key) || null }));
    }, [state]);

    if (!state && !error) {
        return (
            <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box sx={{ width: "100%", minWidth: 0 }}>
            <PageHeader
                title="Investments"
                subtitle="Experiment 1: три незалежні інвестиційні sandbox-рахунки. Без реальних брокерських операцій."
            />

            {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>{error}</Alert>}

            <Alert severity="info" sx={{ mb: 3, borderRadius: 3 }}>
                Simulation only. Defensive, Balanced і Growth мають окремі cash, NAV, позиції, P&amp;L та drawdown.
            </Alert>

            <Box sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" },
                gap: 2,
                mb: 3,
            }}>
                <MetricCard label="Investments ledgers" value="3" caption="Defensive / Balanced / Growth" />
                <MetricCard label="Старт кожного" value="$5,000" caption="Незалежний капітал" />
                <MetricCard label="Внесок кожного" value="$2,000 / міс" caption="Незалежно для кожного ledger" />
                <MetricCard label="Режим" value="Simulation" caption="Жодних реальних ордерів" />
            </Box>

            <Typography variant="h5" sx={{ mb: 2, fontWeight: 700 }}>
                Інвестиційні рахунки
            </Typography>

            <Box sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", lg: "repeat(3, minmax(0, 1fr))" },
                gap: 2,
            }}>
                {accounts.map((account) => {
                    const data = account.data;
                    const positions = data?.positions || [];
                    return (
                        <Paper key={account.key} variant="outlined" sx={{ p: 2.5, borderRadius: 3, minWidth: 0 }}>
                            <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
                                <Box>
                                    <Typography variant="h6" sx={{ fontWeight: 700 }}>{account.name}</Typography>
                                    <Typography variant="body2" color="text.secondary">{account.key}</Typography>
                                </Box>
                                <Chip label={account.risk} size="small" variant="outlined" />
                            </Stack>

                            {!data ? (
                                <Alert severity="warning">Ledger відсутній у Experiment1 API.</Alert>
                            ) : (
                                <Stack spacing={1.25}>
                                    <Typography>Cash: <strong>{usd(data.cash)}</strong></Typography>
                                    <Typography>NAV: <strong>{usd(data.last_equity)}</strong></Typography>
                                    <Typography>Realized P&amp;L: <strong>{usd(data.realized_pnl)}</strong></Typography>
                                    <Typography>Fees: <strong>{usd(data.fees_paid)}</strong></Typography>
                                    <Typography>Max drawdown: <strong>{usd(data.max_drawdown)}</strong></Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Щомісячний внесок: {usd(MONTHLY_CONTRIBUTION)}
                                    </Typography>

                                    <Box sx={{ pt: 1 }}>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Позиції</Typography>
                                        {positions.length === 0 ? (
                                            <Typography variant="body2" color="text.secondary">Позицій немає</Typography>
                                        ) : positions.map((position) => (
                                            <Paper key={`${account.key}-${position.symbol}`} variant="outlined" sx={{ p: 1.25, mb: 1, borderRadius: 2 }}>
                                                <Typography sx={{ fontWeight: 700 }}>{position.symbol}</Typography>
                                                <Typography variant="body2">
                                                    {position.quantity} × {usd(position.average_price)} · notional {usd(position.notional)}
                                                </Typography>
                                            </Paper>
                                        ))}
                                    </Box>
                                </Stack>
                            )}
                        </Paper>
                    );
                })}
            </Box>
        </Box>
    );
}
