import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Typography,
} from "@mui/material";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";

import {
    useEffect,
    useMemo,
    useState,
} from "react";

import {
    extractApiError,
    getLatestScan,
    getScanSignals,
} from "../api/researchApi";


const FILTERS = [
    { value: "all", label: "All signals" },
    { value: "rejected", label: "Rejected" },
    { value: "created", label: "Created" },
    { value: "conflict", label: "Direction conflict" },
    { value: "risk", label: "Risk geometry" },
    { value: "elite", label: "Elite" },
];

const DIRECTION_COLORS = {
    LONG: "success",
    SHORT: "error",
};

const STATUS_COLORS = {
    created: "success",
    rejected: "error",
    skipped: "warning",
    candidate: "info",
};


function formatDate(value) {
    if (!value) {
        return "-";
    }

    try {
        return new Intl.DateTimeFormat(
            "uk-UA",
            {
                dateStyle: "short",
                timeStyle: "medium",
            },
        ).format(new Date(value));
    } catch {
        return value;
    }
}


function formatNumber(value, digits = 2) {
    if (
        value === null
        || value === undefined
        || Number.isNaN(Number(value))
    ) {
        return "-";
    }

    return Number(value).toFixed(digits);
}


function formatPercent(value) {
    if (
        value === null
        || value === undefined
        || Number.isNaN(Number(value))
    ) {
        return "-";
    }

    return `${Number(value).toFixed(1)}%`;
}


function formatPrice(value) {
    if (
        value === null
        || value === undefined
        || Number.isNaN(Number(value))
    ) {
        return "-";
    }

    const numericValue = Number(value);

    if (Math.abs(numericValue) < 0.01) {
        return numericValue.toPrecision(8);
    }

    if (Math.abs(numericValue) < 1) {
        return numericValue.toFixed(6);
    }

    return numericValue.toFixed(4);
}


function includesText(value, text) {
    if (!value) {
        return false;
    }

    return String(value).toLowerCase().includes(text.toLowerCase());
}


function isDirectionConflict(signal) {
    return Boolean(
        signal?.metadata?.direction_conflict
        || includesText(signal?.rejected_reason, "direction conflict")
        || signal?.reasons?.some(
            (reason) => includesText(reason, "direction conflict"),
        ),
    );
}


function isRiskGeometry(signal) {
    return Boolean(
        includesText(signal?.rejected_reason, "risk geometry")
        || includesText(signal?.research_skipped, "risk geometry"),
    );
}


function filterSignal(signal, filter) {
    if (filter === "all") {
        return true;
    }

    if (filter === "conflict") {
        return isDirectionConflict(signal);
    }

    if (filter === "risk") {
        return isRiskGeometry(signal);
    }

    if (filter === "elite") {
        return Boolean(signal.is_elite);
    }

    return signal.status === filter;
}


function signalGroupKey(signal) {
    return [
        signal.symbol || "UNKNOWN",
        signal.market || "unknown",
        signal.timeframe || "unknown",
    ].join("|");
}


function groupSignals(signals) {
    const groups = new Map();

    signals.forEach((signal) => {
        const key = signalGroupKey(signal);

        if (!groups.has(key)) {
            groups.set(
                key,
                {
                    key,
                    symbol: signal.symbol || "UNKNOWN",
                    market: signal.market || "unknown",
                    timeframe: signal.timeframe || "unknown",
                    signals: [],
                },
            );
        }

        groups.get(key).signals.push(signal);
    });

    return Array.from(groups.values()).map((group) => {
        const longSignals = group.signals.filter(
            (signal) => signal.direction === "LONG",
        );

        const shortSignals = group.signals.filter(
            (signal) => signal.direction === "SHORT",
        );

        const rejectedSignals = group.signals.filter(
            (signal) => signal.status === "rejected",
        );

        const createdSignals = group.signals.filter(
            (signal) => signal.status === "created",
        );

        const conflictSignals = group.signals.filter(
            isDirectionConflict,
        );

        const riskSignals = group.signals.filter(
            isRiskGeometry,
        );

        const strategies = Array.from(
            new Set(
                group.signals.map(
                    (signal) => signal.strategy,
                ).filter(Boolean),
            ),
        );

        return {
            ...group,
            longCount: longSignals.length,
            shortCount: shortSignals.length,
            rejectedCount: rejectedSignals.length,
            createdCount: createdSignals.length,
            conflictCount: conflictSignals.length,
            riskCount: riskSignals.length,
            strategies,
            conflictMetadata: conflictSignals[0]?.metadata || null,
        };
    }).sort((a, b) => {
        if (b.conflictCount !== a.conflictCount) {
            return b.conflictCount - a.conflictCount;
        }

        if (b.riskCount !== a.riskCount) {
            return b.riskCount - a.riskCount;
        }

        return b.signals.length - a.signals.length;
    });
}


function getTopReason(signal) {
    if (
        Array.isArray(signal.reasons)
        && signal.reasons.length > 0
    ) {
        return signal.reasons[0];
    }

    if (signal.rejected_reason) {
        return signal.rejected_reason;
    }

    return "No reason provided.";
}


function ChipWrap({ children }) {
    return (
        <Box
            sx={{
                display: "flex",
                flexWrap: "wrap",
                gap: 0.75,
                minWidth: 0,
            }}
        >
            {children}
        </Box>
    );
}


function StatCard({
    label,
    value,
    helper,
}) {
    return (
        <Card
            variant="outlined"
            sx={{
                borderRadius: 4,
                height: "100%",
                minWidth: 0,
            }}
        >
            <CardContent
                sx={{
                    p: 2,
                    "&:last-child": {
                        pb: 2,
                    },
                }}
            >
                <Typography
                    variant="caption"
                    color="text.secondary"
                    fontWeight={700}
                >
                    {label}
                </Typography>

                <Typography
                    variant="h5"
                    fontWeight={900}
                    sx={{
                        lineHeight: 1.1,
                        mt: 0.75,
                    }}
                >
                    {value}
                </Typography>

                {helper ? (
                    <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                            display: "block",
                            mt: 0.75,
                        }}
                    >
                        {helper}
                    </Typography>
                ) : null}
            </CardContent>
        </Card>
    );
}


function DirectionConflictSummary({ metadata }) {
    if (!metadata?.direction_conflict) {
        return null;
    }

    const longStrategies = (
        metadata.conflict_long_strategies || []
    ).join(", ");

    const shortStrategies = (
        metadata.conflict_short_strategies || []
    ).join(", ");

    return (
        <Box
            sx={{
                mt: 2,
                p: 2,
                borderRadius: 3,
                bgcolor: "rgba(255, 171, 64, 0.16)",
                border: "1px solid rgba(255, 171, 64, 0.35)",
                maxWidth: "100%",
                overflow: "hidden",
            }}
        >
            <Typography
                variant="subtitle2"
                fontWeight={900}
                gutterBottom
            >
                Direction conflict summary
            </Typography>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: "repeat(3, minmax(0, 1fr))",
                    },
                    gap: 1.5,
                }}
            >
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        LONG side
                    </Typography>

                    <Typography fontWeight={900}>
                        Score {formatNumber(metadata.conflict_long_score)}
                    </Typography>

                    <Typography
                        variant="caption"
                        sx={{
                            overflowWrap: "anywhere",
                        }}
                    >
                        {longStrategies || "-"}
                    </Typography>
                </Box>

                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        SHORT side
                    </Typography>

                    <Typography fontWeight={900}>
                        Score {formatNumber(metadata.conflict_short_score)}
                    </Typography>

                    <Typography
                        variant="caption"
                        sx={{
                            overflowWrap: "anywhere",
                        }}
                    >
                        {shortStrategies || "-"}
                    </Typography>
                </Box>

                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Delta / Required
                    </Typography>

                    <Typography fontWeight={900}>
                        {formatNumber(metadata.conflict_score_delta)}
                        {" / "}
                        {formatNumber(metadata.conflict_min_score_delta)}
                    </Typography>

                    <Typography
                        variant="caption"
                        sx={{
                            overflowWrap: "anywhere",
                        }}
                    >
                        {metadata.conflict_resolution || "mixed_rejected"}
                    </Typography>
                </Box>
            </Box>
        </Box>
    );
}


function SignalRow({ signal }) {
    const extraReasons = (
        Array.isArray(signal.reasons)
            ? signal.reasons.slice(1, 5)
            : []
    );

    return (
        <Card
            variant="outlined"
            sx={{
                borderRadius: 3,
                bgcolor: "background.default",
                maxWidth: "100%",
                overflow: "hidden",
            }}
        >
            <CardContent
                sx={{
                    p: 2,
                    "&:last-child": {
                        pb: 2,
                    },
                }}
            >
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: {
                            xs: "1fr",
                            lg: "minmax(0, 1fr) 420px",
                        },
                        gap: 2,
                        alignItems: "start",
                        minWidth: 0,
                    }}
                >
                    <Box sx={{ minWidth: 0 }}>
                        <ChipWrap>
                            <Chip
                                size="small"
                                label={signal.strategy || "Unknown"}
                                variant="outlined"
                            />

                            <Chip
                                size="small"
                                label={signal.direction || "-"}
                                color={
                                    DIRECTION_COLORS[signal.direction]
                                    || "default"
                                }
                            />

                            <Chip
                                size="small"
                                label={signal.status || "unknown"}
                                color={
                                    STATUS_COLORS[signal.status]
                                    || "default"
                                }
                                variant="outlined"
                            />

                            {signal.is_elite ? (
                                <Chip
                                    size="small"
                                    label="ELITE"
                                    color="secondary"
                                />
                            ) : null}

                            {isDirectionConflict(signal) ? (
                                <Chip
                                    size="small"
                                    label="Conflict"
                                    color="warning"
                                />
                            ) : null}

                            {isRiskGeometry(signal) ? (
                                <Chip
                                    size="small"
                                    label="Risk block"
                                    color="error"
                                    variant="outlined"
                                />
                            ) : null}
                        </ChipWrap>

                        <Typography
                            variant="body2"
                            fontWeight={800}
                            sx={{
                                mt: 1,
                                overflowWrap: "anywhere",
                            }}
                        >
                            {getTopReason(signal)}
                        </Typography>

                        <Typography
                            variant="caption"
                            color="text.secondary"
                        >
                            Created: {formatDate(signal.created_at)}
                        </Typography>
                    </Box>

                    <Box
                        sx={{
                            display: "grid",
                            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                            gap: 1,
                            minWidth: 0,
                        }}
                    >
                        <Box>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Score
                            </Typography>

                            <Typography fontWeight={900}>
                                {formatNumber(signal.score)}
                            </Typography>
                        </Box>

                        <Box>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Prob.
                            </Typography>

                            <Typography fontWeight={900}>
                                {formatPercent(signal.probability)}
                            </Typography>
                        </Box>

                        <Box>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Entry
                            </Typography>

                            <Typography fontWeight={900}>
                                {formatPrice(signal.entry_price)}
                            </Typography>
                        </Box>

                        <Box>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                RR
                            </Typography>

                            <Typography fontWeight={900}>
                                {formatNumber(signal.risk_reward)}
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                {signal.rejected_reason ? (
                    <Alert
                        severity={
                            isDirectionConflict(signal)
                                ? "warning"
                                : "error"
                        }
                        sx={{
                            mt: 1.5,
                            borderRadius: 2,
                            "& .MuiAlert-message": {
                                overflowWrap: "anywhere",
                            },
                        }}
                    >
                        {signal.rejected_reason}
                    </Alert>
                ) : null}

                {extraReasons.length > 0 ? (
                    <Box sx={{ mt: 1.5 }}>
                        <ChipWrap>
                            {extraReasons.map((reason) => (
                                <Chip
                                    key={reason}
                                    size="small"
                                    label={reason}
                                    variant="outlined"
                                />
                            ))}
                        </ChipWrap>
                    </Box>
                ) : null}
            </CardContent>
        </Card>
    );
}


function SignalGroup({ group, defaultExpanded }) {
    return (
        <Accordion
            defaultExpanded={defaultExpanded}
            disableGutters
            sx={{
                borderRadius: 3,
                overflow: "hidden",
                border: "1px solid",
                borderColor: "divider",
                maxWidth: "100%",
                "&:before": {
                    display: "none",
                },
            }}
        >
            <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                sx={{
                    bgcolor: "background.paper",
                    px: 2,
                }}
            >
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: {
                            xs: "1fr",
                            lg: "260px minmax(0, 1fr)",
                        },
                        gap: 2,
                        alignItems: "center",
                        width: "100%",
                        minWidth: 0,
                        pr: 2,
                    }}
                >
                    <Box sx={{ minWidth: 0 }}>
                        <Typography
                            variant="h6"
                            fontWeight={900}
                            sx={{
                                lineHeight: 1.1,
                                overflowWrap: "anywhere",
                            }}
                        >
                            {group.symbol}
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            {group.market.toUpperCase()}
                            {" - "}
                            {group.timeframe}
                            {" - "}
                            {group.signals.length}
                            {" signals"}
                        </Typography>
                    </Box>

                    <ChipWrap>
                        <Chip
                            size="small"
                            label={`LONG ${group.longCount}`}
                            color="success"
                            variant="outlined"
                        />

                        <Chip
                            size="small"
                            label={`SHORT ${group.shortCount}`}
                            color="error"
                            variant="outlined"
                        />

                        {group.conflictCount > 0 ? (
                            <Chip
                                size="small"
                                label={`Conflicts ${group.conflictCount}`}
                                color="warning"
                            />
                        ) : null}

                        {group.riskCount > 0 ? (
                            <Chip
                                size="small"
                                label={`Risk ${group.riskCount}`}
                                color="error"
                                variant="outlined"
                            />
                        ) : null}

                        {group.createdCount > 0 ? (
                            <Chip
                                size="small"
                                label={`Created ${group.createdCount}`}
                                color="success"
                            />
                        ) : null}

                        {group.strategies.slice(0, 5).map((strategy) => (
                            <Chip
                                key={strategy}
                                size="small"
                                label={strategy}
                                variant="outlined"
                            />
                        ))}
                    </ChipWrap>
                </Box>
            </AccordionSummary>

            <AccordionDetails
                sx={{
                    p: 2,
                    pt: 0,
                }}
            >
                <DirectionConflictSummary
                    metadata={group.conflictMetadata}
                />

                <Box
                    sx={{
                        display: "grid",
                        gap: 1.25,
                        mt: group.conflictMetadata ? 2 : 0,
                    }}
                >
                    {group.signals.map((signal) => (
                        <SignalRow
                            key={signal.id}
                            signal={signal}
                        />
                    ))}
                </Box>
            </AccordionDetails>
        </Accordion>
    );
}


export default function Signals() {
    const [
        loading,
        setLoading,
    ] = useState(true);

    const [
        error,
        setError,
    ] = useState("");

    const [
        latestScan,
        setLatestScan,
    ] = useState(null);

    const [
        signals,
        setSignals,
    ] = useState([]);

    const [
        total,
        setTotal,
    ] = useState(0);

    const [
        filter,
        setFilter,
    ] = useState("all");

    async function loadData() {
        setLoading(true);
        setError("");

        try {
            const latestScanResponse = await getLatestScan();
            const scanRun = latestScanResponse.scan_run;

            setLatestScan(scanRun || null);

            if (!scanRun?.id) {
                setSignals([]);
                setTotal(0);
                return;
            }

            const signalsResponse = await getScanSignals(
                scanRun.id,
                {
                    limit: 100,
                },
            );

            setSignals(signalsResponse.signals || []);
            setTotal(signalsResponse.total || 0);
        } catch (requestError) {
            setError(
                extractApiError(requestError),
            );
        } finally {
            setLoading(false);
        }
    }

    useEffect(
        () => {
            loadData();
        },
        [],
    );

    const filteredSignals = useMemo(
        () => signals.filter(
            (signal) => filterSignal(signal, filter),
        ),
        [
            signals,
            filter,
        ],
    );

    const groupedSignals = useMemo(
        () => groupSignals(filteredSignals),
        [
            filteredSignals,
        ],
    );

    const stats = useMemo(
        () => {
            const rejected = signals.filter(
                (signal) => signal.status === "rejected",
            ).length;

            const created = signals.filter(
                (signal) => signal.status === "created",
            ).length;

            const conflicts = signals.filter(
                isDirectionConflict,
            ).length;

            const risks = signals.filter(
                isRiskGeometry,
            ).length;

            return {
                rejected,
                created,
                conflicts,
                risks,
            };
        },
        [
            signals,
        ],
    );

    return (
        <Box
            sx={{
                maxWidth: "100%",
                overflowX: "hidden",
            }}
        >
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "1fr",
                        lg: "minmax(0, 1fr) 370px",
                    },
                    gap: 2,
                    alignItems: "start",
                    mb: 3,
                }}
            >
                <Box sx={{ minWidth: 0 }}>
                    <Typography
                        variant="h4"
                        fontWeight={900}
                    >
                        Signals Journal
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                            mt: 0.5,
                            maxWidth: 900,
                        }}
                    >
                        Journal of detected signals, rejected setups,
                        direction conflicts, risk geometry blocks and raw setup reasons.
                    </Typography>
                </Box>

                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: "minmax(0, 1fr) 120px",
                        gap: 1,
                        minWidth: 0,
                    }}
                >
                    <FormControl
                        size="small"
                        fullWidth
                    ><Select
                            value={filter}
                            onChange={(event) => {
                                setFilter(event.target.value);
                            }}
                        >
                            {FILTERS.map((item) => (
                                <MenuItem
                                    key={item.value}
                                    value={item.value}
                                >
                                    {item.label}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    <Button
                        variant="contained"
                        startIcon={<RefreshIcon />}
                        onClick={loadData}
                        disabled={loading}
                        sx={{
                            minWidth: 0,
                        }}
                    >
                        Refresh
                    </Button>
                </Box>
            </Box>

            {error ? (
                <Alert
                    severity="error"
                    sx={{
                        mb: 3,
                        borderRadius: 2,
                    }}
                >
                    {error}
                </Alert>
            ) : null}

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        md: "repeat(3, minmax(0, 1fr))",
                        xl: "repeat(6, minmax(0, 1fr))",
                    },
                    gap: 2,
                    mb: 3,
                }}
            >
                <StatCard
                    label="Latest scan"
                    value={latestScan?.timeframe || "-"}
                    helper={formatDate(latestScan?.finished_at)}
                />

                <StatCard
                    label="Total"
                    value={total}
                    helper={`${groupedSignals.length} groups`}
                />

                <StatCard
                    label="Rejected"
                    value={stats.rejected}
                />

                <StatCard
                    label="Created"
                    value={stats.created}
                />

                <StatCard
                    label="Conflicts"
                    value={stats.conflicts}
                />

                <StatCard
                    label="Risk blocks"
                    value={stats.risks}
                />
            </Box>

            {loading ? (
                <Box
                    sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        py: 8,
                    }}
                >
                    <CircularProgress />
                </Box>
            ) : null}

            {!loading && groupedSignals.length === 0 ? (
                <Alert
                    severity="info"
                    sx={{
                        borderRadius: 2,
                    }}
                >
                    No signals for the selected filter.
                </Alert>
            ) : null}

            {!loading && groupedSignals.length > 0 ? (
                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                    }}
                >
                    {groupedSignals.map((group, index) => (
                        <SignalGroup
                            key={group.key}
                            group={group}
                            defaultExpanded={index < 2}
                        />
                    ))}
                </Box>
            ) : null}
        </Box>
    );
}