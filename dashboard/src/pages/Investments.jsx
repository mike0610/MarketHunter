import {
    Alert,
    Box,
    Chip,
    LinearProgress,
    Paper,
    Stack,
    Typography,
} from "@mui/material";

import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/layout/MetricCard";


const STARTING_CAPITAL = 5000;
const MONTHLY_CONTRIBUTION = 2000;

const PORTFOLIO_PROFILES = [
    {
        name: "Defensive",
        risk: "Низький ризик",
        horizon: "1–3 роки",
        purpose: "Профіль для рішень із пріоритетом збереження капіталу та нижчої волатильності.",
        status: "Очікує рішень GIL",
    },
    {
        name: "Balanced",
        risk: "Середній ризик",
        horizon: "5–10 років",
        purpose: "Профіль для балансу росту капіталу та захисних активів.",
        status: "Очікує рішень GIL",
    },
    {
        name: "Growth",
        risk: "Високий ризик",
        horizon: "10+ років",
        purpose: "Профіль для довгострокового зростання з вищою допустимою просадкою.",
        status: "Очікує рішень GIL",
    },
];


function formatUsd(value) {
    return new Intl.NumberFormat(
        "en-US",
        {
            style: "currency",
            currency: "USD",
            maximumFractionDigits: 0,
        },
    ).format(value);
}


export default function Investments() {
    return (
        <Box sx={{ width: "100%", minWidth: 0 }}>
            <PageHeader
                title="Investments"
                subtitle="Experiment 1: один окремий інвестиційний sandbox-рахунок. Без реальних брокерських операцій."
            />

            <Alert
                severity="info"
                sx={{ mb: 3, borderRadius: 3 }}
            >
                Старт експерименту не означає BUY. Рішення BUY / SELL / WAIT / HOLD приймаються окремо, а непроінвестований капітал може залишатися cash. Ринкові ціни, комісії, FX та податки не вигадуються.
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
                <MetricCard
                    label="Investments account"
                    value={formatUsd(STARTING_CAPITAL)}
                    caption="Один незалежний рахунок Experiment 1"
                />
                <MetricCard
                    label="Щомісячний внесок"
                    value={formatUsd(MONTHLY_CONTRIBUTION)}
                    caption="Може накопичуватися як cash"
                />
                <MetricCard
                    label="Режим"
                    value="Simulation"
                    caption="Жодних реальних ордерів"
                />
                <MetricCard
                    label="Поточна дія"
                    value="WAIT"
                    caption="До появи перевіреного рішення"
                />
            </Box>

            <Typography
                variant="h5"
                sx={{ mb: 2, fontWeight: 700 }}
            >
                Профілі рішень
            </Typography>

            <Alert severity="warning" sx={{ mb: 2, borderRadius: 3 }}>
                Defensive / Balanced / Growth не є трьома окремими рахунками по $5,000. Це лише профілі для порівняння рішень усередині одного Investments account.
            </Alert>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        lg: "repeat(3, minmax(0, 1fr))",
                    },
                    gap: 2,
                }}
            >
                {PORTFOLIO_PROFILES.map((profile) => (
                    <Paper
                        key={profile.name}
                        variant="outlined"
                        sx={{
                            p: 2.5,
                            borderRadius: 3,
                            minWidth: 0,
                        }}
                    >
                        <Stack
                            direction="row"
                            spacing={1}
                            sx={{
                                justifyContent: "space-between",
                                alignItems: "flex-start",
                                mb: 2,
                            }}
                        >
                            <Box sx={{ minWidth: 0 }}>
                                <Typography
                                    variant="h6"
                                    sx={{ fontWeight: 700 }}
                                >
                                    {profile.name}
                                </Typography>
                                <Typography
                                    variant="body2"
                                    color="text.secondary"
                                >
                                    {profile.horizon}
                                </Typography>
                            </Box>

                            <Chip
                                label={profile.risk}
                                size="small"
                                variant="outlined"
                            />
                        </Stack>

                        <Typography
                            variant="body2"
                            sx={{ mb: 2 }}
                        >
                            {profile.purpose}
                        </Typography>

                        <Box>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Готовність
                            </Typography>
                            <LinearProgress
                                variant="determinate"
                                value={25}
                                sx={{ mt: 0.75, mb: 0.75, borderRadius: 999 }}
                            />
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {profile.status}
                            </Typography>
                        </Box>
                    </Paper>
                ))}
            </Box>
        </Box>
    );
}
