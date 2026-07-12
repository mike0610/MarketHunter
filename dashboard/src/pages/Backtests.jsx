import { useState } from "react";

import {
    Alert,
    Box,
    Button,
    CircularProgress,
    Paper,
    Stack,
    Typography,
} from "@mui/material";

import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { extractApiError } from "../api/researchApi";
import { runBacktest } from "../api/backtestApi";

import PageHeader from "../components/layout/PageHeader";


export default function Backtests() {
    const [running, setRunning] = useState(false);
    const [error, setError] = useState("");
    const [lastMessage, setLastMessage] = useState("");

    async function handleRun() {
        try {
            setRunning(true);
            setError("");

            const response = await runBacktest();

            setLastMessage(response?.message || "Запит надіслано.");
        } catch (runError) {
            setError(extractApiError(runError));
        } finally {
            setRunning(false);
        }
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
                title="Backtests"
                subtitle="Історичні тести стратегій. Поки в розробці."
            />

            <Alert
                severity="info"
                sx={{ mb: 3 }}
            >
                Бекенд-модулі для бектестів (`backtesting/`, `optimizer/`
                з grid search і walk-forward) уже існують у репозиторії,
                але ще не підключені до API — немає ендпоінта, що реально
                запускає бектест і зберігає результати. Кнопка нижче
                звертається до наявної заглушки `/backtest/run`, яка лише
                підтверджує запит, не виконує розрахунків.
            </Alert>

            {error && (
                <Alert
                    severity="warning"
                    sx={{ mb: 3 }}
                >
                    {error}
                </Alert>
            )}

            <Paper
                variant="outlined"
                sx={{
                    p: 4,
                    borderRadius: 4,
                }}
            >
                <Stack
                    spacing={2}
                    alignItems="flex-start"
                >
                    <Typography
                        variant="h6"
                        fontWeight={700}
                    >
                        Запуск (заглушка)
                    </Typography>

                    <Typography color="text.secondary">
                        Реальних результатів бектесту тут поки не буде —
                        це перевіряє лише зв'язок із бекендом.
                    </Typography>

                    <Button
                        variant="outlined"
                        startIcon={
                            running
                                ? (
                                    <CircularProgress
                                        size={18}
                                        color="inherit"
                                    />
                                )
                                : <PlayArrowIcon />
                        }
                        onClick={handleRun}
                        disabled={running}
                    >
                        Перевірити ендпоінт
                    </Button>

                    {lastMessage && (
                        <Alert severity="success">
                            {lastMessage}
                        </Alert>
                    )}
                </Stack>
            </Paper>
        </Box>
    );
}
