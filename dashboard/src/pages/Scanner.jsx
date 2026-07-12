import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Paper,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";

import { useNavigate } from "react-router-dom";

import {
    extractApiError,
    getScanRuns,
} from "../api/researchApi";

import PageHeader from "../components/layout/PageHeader";


const STATUS_COLORS = {
    completed: "success",
    running: "info",
    failed: "error",
};


function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "—";
    }

    return date.toLocaleString("uk-UA");
}


export default function Scanner() {
    const navigate = useNavigate();

    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [scanRuns, setScanRuns] = useState([]);

    const loadData = useCallback(
        async () => {
            const response = await getScanRuns({
                limit: 20,
            });

            setScanRuns(Array.isArray(response?.scan_runs) ? response.scan_runs : []);
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

    return (
        <Box
            sx={{
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
            }}
        >
            <PageHeader
                title="Scanner"
                subtitle="Історія сканувань ринку. Останні сигнали дивись на сторінці Signals."
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

            {scanRuns.length === 0 ? (
                <Paper
                    variant="outlined"
                    sx={{
                        p: 4,
                        borderRadius: 4,
                        textAlign: "center",
                    }}
                >
                    <Typography color="text.secondary">
                        Ще жодного скану не зафіксовано.
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
                    <TableContainer>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>Розпочато</TableCell>
                                    <TableCell>Статус</TableCell>
                                    <TableCell align="right">Символів</TableCell>
                                    <TableCell align="right">Кандидатів</TableCell>
                                    <TableCell align="right">Research-угод</TableCell>
                                    <TableCell align="right">Elite</TableCell>
                                    <TableCell>Timeframe</TableCell>
                                </TableRow>
                            </TableHead>

                            <TableBody>
                                {scanRuns.map((scanRun) => (
                                    <TableRow
                                        key={scanRun.id}
                                        hover
                                        onClick={() => navigate("/signals")}
                                        sx={{ cursor: "pointer" }}
                                    >
                                        <TableCell>
                                            {formatDateTime(scanRun.started_at)}
                                        </TableCell>

                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={scanRun.status}
                                                color={
                                                    STATUS_COLORS[scanRun.status]
                                                    || "default"
                                                }
                                            />
                                        </TableCell>

                                        <TableCell align="right">
                                            {scanRun.symbols_scanned}
                                        </TableCell>

                                        <TableCell align="right">
                                            {scanRun.candidate_signals}
                                        </TableCell>

                                        <TableCell align="right">
                                            {scanRun.research_trades_created}
                                        </TableCell>

                                        <TableCell align="right">
                                            {scanRun.elite_signals_found}
                                        </TableCell>

                                        <TableCell>
                                            {scanRun.timeframe}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </Paper>
            )}

            <Stack
                sx={{ mt: 2 }}
            >
                <Typography
                    variant="caption"
                    color="text.secondary"
                >
                    Ручний запуск сканування з дашборду поки не підключено
                    до реального сканера (бекенд-ендпоінт `/scanner/run` —
                    заглушка). Сканування зараз запускає continuous worker.
                </Typography>
            </Stack>
        </Box>
    );
}
