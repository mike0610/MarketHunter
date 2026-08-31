import {
    useEffect,
    useState,
} from "react";

import {
    AppBar,
    Chip,
    IconButton,
    Stack,
    Toolbar,
    Typography,
} from "@mui/material";

import MenuIcon from "@mui/icons-material/Menu";

import { getHealth } from "../../api/healthApi";
import { getWorkerStatus } from "../../api/researchApi";


const POLL_INTERVAL_MS = 30_000;

const WORKER_STATE_LABELS = {
    running: "Воркер працює",
    waiting: "Воркер очікує",
    failed: "Воркер: помилка",
    stopped: "Воркер зупинений",
    not_started: "Воркер не запущено",
};

const WORKER_STATE_COLORS = {
    running: "success",
    waiting: "info",
    failed: "error",
    stopped: "default",
    not_started: "default",
};

function workerChipProps(workerState) {
    const normalized = String(workerState || "").trim().toLowerCase();

    return {
        label: WORKER_STATE_LABELS[normalized] || "Воркер: невідомо",
        color: WORKER_STATE_COLORS[normalized] || "default",
    };
}

export default function AppTopBar({ onMenuClick }) {
    const [apiOnline, setApiOnline] = useState(null);
    const [workerState, setWorkerState] = useState(null);

    useEffect(
        () => {
            let active = true;

            async function poll() {
                try {
                    await getHealth();
                    if (active) {
                        setApiOnline(true);
                    }
                } catch {
                    if (active) {
                        setApiOnline(false);
                    }
                }

                try {
                    const status = await getWorkerStatus();
                    if (active) {
                        setWorkerState(status?.state ?? null);
                    }
                } catch {
                    if (active) {
                        setWorkerState(null);
                    }
                }
            }

            void poll();
            const intervalId = setInterval(poll, POLL_INTERVAL_MS);

            return () => {
                active = false;
                clearInterval(intervalId);
            };
        },
        [],
    );

    const workerChip = workerChipProps(workerState);

    return (
        <AppBar position="static" elevation={1}>
            <Toolbar sx={{ gap: 1 }}>
                <IconButton
                    color="inherit"
                    edge="start"
                    aria-label="Відкрити меню"
                    onClick={onMenuClick}
                    sx={{ display: { xs: "inline-flex", md: "none" } }}
                >
                    <MenuIcon />
                </IconButton>

                <Typography
                    variant="h6"
                    sx={{
                        flexGrow: 1,
                        minWidth: 0,
                        fontSize: { xs: "1rem", sm: "1.25rem" },
                        whiteSpace: { xs: "nowrap", sm: "normal" },
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                    }}
                >
                    MarketHunter Terminal
                </Typography>

                <Stack
                    direction="row"
                    spacing={1}
                    sx={{
                        flexShrink: 0,
                        "& .MuiChip-root": {
                            maxWidth: { xs: 104, sm: "none" },
                        },
                        "& .MuiChip-label": {
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                        },
                    }}
                >
                    <Chip
                        size="small"
                        label={
                            apiOnline === null
                                ? "API: перевірка..."
                                : apiOnline
                                    ? "API Connected"
                                    : "API Offline"
                        }
                        color={
                            apiOnline === null
                                ? "default"
                                : apiOnline
                                    ? "success"
                                    : "error"
                        }
                    />

                    <Chip
                        size="small"
                        label={workerChip.label}
                        color={workerChip.color}
                        sx={{ display: { xs: "none", sm: "inline-flex" } }}
                    />
                </Stack>
            </Toolbar>
        </AppBar>
    );
}
