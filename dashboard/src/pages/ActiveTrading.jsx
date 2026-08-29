import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";

import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/layout/MetricCard";

const MARKETS = [
    { name: "Gold", detail: "Gold instruments", state: "Foundation" },
    { name: "US Equities", detail: "Large-cap stocks", state: "Foundation" },
    { name: "US Indices", detail: "Major index instruments", state: "Foundation" },
];

export default function ActiveTrading() {
    return (
        <Box sx={{ width: "100%", minWidth: 0 }}>
            <PageHeader
                title="Active Trading"
                subtitle="Окремий multi-asset контур для золота, акцій та індексів."
            />

            <Alert severity="info" sx={{ mb: 3, borderRadius: 3 }}>
                Тестовий режим. Сигнали та позиції зʼявляться тільки після підключення перевірених ринкових даних.
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
                <MetricCard label="Режим" value="Paper" caption="Тестовий торговий контур" />
                <MetricCard label="Класи активів" value="3" caption="Gold / Equities / Indices" />
                <MetricCard label="Активні позиції" value="—" caption="Очікують market data" />
                <MetricCard label="Сетапи" value="—" caption="Очікують scanner integration" />
            </Box>

            <Typography variant="h5" sx={{ mb: 2, fontWeight: 700 }}>
                Ринки
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
                {MARKETS.map((market) => (
                    <Paper key={market.name} variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
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
                            Окрема ринкова сесія, ідентифікація інструментів та статистика будуть підключені наступними зрізами.
                        </Typography>
                    </Paper>
                ))}
            </Box>
        </Box>
    );
}
