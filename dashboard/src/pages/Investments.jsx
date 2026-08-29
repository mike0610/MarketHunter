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

const PORTFOLIOS = [
    {
        name: "Defensive",
        risk: "Низький ризик",
        horizon: "1–3 роки",
        purpose: "Збереження капіталу та нижча волатильність.",
        status: "Очікує складу від GIL",
    },
    {
        name: "Balanced",
        risk: "Середній ризик",
        horizon: "5–10 років",
        purpose: "Баланс росту капіталу та захисних активів.",
        status: "Очікує складу від GIL",
    },
    {
        name: "Growth",
        risk: "Високий ризик",
        horizon: "10+ років",
        purpose: "Довгострокове зростання з вищою допустимою просадкою.",
        status: "Очікує складу від GIL",
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
                subtitle="Тестовий інвестиційний контур MarketHunter. Paper/sandbox only, без реальних брокерських операцій."
            />

            <Alert
                severity="info"
                sx={{ mb: 3, borderRadius: 3 }}
            >
                Стартуємо з поточного дня. Ринкові ціни, комісії, FX та податки не вигадуються: вони зʼявляться тільки з перевіреного джерела даних.
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
                    label="Стартовий капітал"
                    value={formatUsd(STARTING_CAPITAL)}
                    caption="Початковий внесок у кожен тестовий сценарій"
                />
                <MetricCard
                    label="Щомісячний внесок"
                    value={formatUsd(MONTHLY_CONTRIBUTION)}
                    caption="Плановий регулярний cash flow"
                />
                <MetricCard
                    label="Режим"
                    value="Sandbox"
                    caption="Жодних реальних ордерів"
                />
                <MetricCard
                    label="Портфелі"
                    value="3"
                    caption="Defensive / Balanced / Growth"
                />
            </Box>

            <Typography
                variant="h5"
                sx={{ mb: 2, fontWeight: 700 }}
            >
                Гіпотетичні портфелі
            </Typography>

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
                {PORTFOLIOS.map((portfolio) => (
                    <Paper
                        key={portfolio.name}
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
                                    {portfolio.name}
                                </Typography>
                                <Typography
                                    variant="body2"
                                    color="text.secondary"
                                >
                                    {portfolio.horizon}
                                </Typography>
                            </Box>

                            <Chip
                                label={portfolio.risk}
                                size="small"
                                variant="outlined"
                            />
                        </Stack>

                        <Typography
                            variant="body2"
                            sx={{ mb: 2 }}
                        >
                            {portfolio.purpose}
                        </Typography>

                        <Stack spacing={1.5}>
                            <Box>
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    Початковий NAV
                                </Typography>
                                <Typography sx={{ fontWeight: 600 }}>
                                    {formatUsd(STARTING_CAPITAL)}
                                </Typography>
                            </Box>

                            <Box>
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    Наступний внесок
                                </Typography>
                                <Typography sx={{ fontWeight: 600 }}>
                                    {formatUsd(MONTHLY_CONTRIBUTION)} / місяць
                                </Typography>
                            </Box>

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
                                    {portfolio.status}
                                </Typography>
                            </Box>
                        </Stack>
                    </Paper>
                ))}
            </Box>
        </Box>
    );
}
