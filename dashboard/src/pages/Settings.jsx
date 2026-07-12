import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    Alert,
    Box,
    CircularProgress,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableRow,
    Typography,
} from "@mui/material";

import { extractApiError } from "../api/researchApi";
import { getConfig } from "../api/configApi";

import PageHeader from "../components/layout/PageHeader";


const SENSITIVE_KEY_PATTERN = /key|secret|token|password/i;


function formatValue(key, value) {
    if (SENSITIVE_KEY_PATTERN.test(key)) {
        return "••••••••";
    }

    if (value === null || value === undefined) {
        return "—";
    }

    if (typeof value === "boolean") {
        return value ? "увімкнено" : "вимкнено";
    }

    if (typeof value === "object") {
        return JSON.stringify(value);
    }

    return String(value);
}


export default function Settings() {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [config, setConfig] = useState(null);

    const loadData = useCallback(
        async () => {
            const data = await getConfig();

            setConfig(data && typeof data === "object" ? data : {});
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

    const entries = Object.entries(config || {});

    return (
        <Box
            sx={{
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
            }}
        >
            <PageHeader
                title="Settings"
                subtitle="Поточна конфігурація бекенду (тільки читання)."
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

            <Alert
                severity="info"
                sx={{ mb: 3 }}
            >
                Редагування конфігурації з дашборду ще не реалізовано —
                значення нижче читаються напряму з `/config` (реальний
                бекенд-ендпоінт), зміни поки робляться через `.env` файл
                і перезапуск застосунку.
            </Alert>

            {entries.length === 0 ? (
                <Paper
                    variant="outlined"
                    sx={{
                        p: 4,
                        borderRadius: 4,
                        textAlign: "center",
                    }}
                >
                    <Typography color="text.secondary">
                        Конфігурація порожня або недоступна.
                    </Typography>
                </Paper>
            ) : (
                <Paper
                    variant="outlined"
                    sx={{
                        borderRadius: 4,
                        overflow: "hidden",
                    }}
                >
                    <Table size="small">
                        <TableBody>
                            {entries.map(([key, value]) => (
                                <TableRow key={key}>
                                    <TableCell sx={{ fontWeight: 600, width: "40%" }}>
                                        {key}
                                    </TableCell>

                                    <TableCell>
                                        {formatValue(key, value)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Paper>
            )}
        </Box>
    );
}
