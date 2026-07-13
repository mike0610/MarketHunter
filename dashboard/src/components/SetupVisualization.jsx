import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Divider,
    Paper,
    Stack,
    Typography,
} from "@mui/material";


function toNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }

    const converted = Number(value);

    if (Number.isNaN(converted)) {
        return null;
    }

    return converted;
}


function formatPrice(value) {
    const numeric = toNumber(value);

    if (numeric === null) {
        return "—";
    }

    return new Intl.NumberFormat(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: 8,
        },
    ).format(numeric);
}


function formatPercent(value) {
    const numeric = toNumber(value);

    if (numeric === null) {
        return "—";
    }

    return `${numeric.toFixed(2)}%`;
}


function normalizeDirection(direction) {
    return String(direction || "").trim().toUpperCase();
}


function calculateFallbackTarget({
    direction,
    entry,
    stopLoss,
    rr,
}) {
    const risk = Math.abs(entry - stopLoss);

    if (risk <= 0) {
        return null;
    }

    if (normalizeDirection(direction) === "SHORT") {
        return entry - risk * rr;
    }

    return entry + risk * rr;
}


function calculateCurrentRR(trade) {
    const entry = toNumber(trade?.entry_price);
    const stopLoss = toNumber(trade?.stop_loss);
    const takeProfit = toNumber(trade?.take_profit);

    if (
        entry === null
        || stopLoss === null
        || takeProfit === null
        || entry === stopLoss
    ) {
        return null;
    }

    return Math.abs(takeProfit - entry) / Math.abs(entry - stopLoss);
}


function buildTargets({
    trade,
    setup,
}) {
    if (setup?.rr_targets?.length > 0) {
        return setup.rr_targets.map((target) => ({
            rr: toNumber(target.rr),
            price: toNumber(target.price),
            source: "backend",
        }));
    }

    const entry = toNumber(trade?.entry_price);
    const stopLoss = toNumber(trade?.stop_loss);

    if (entry === null || stopLoss === null) {
        return [];
    }

    return [
        1,
        2,
        3,
    ].map((rr) => ({
        rr,
        price: calculateFallbackTarget({
            direction: trade.direction,
            entry,
            stopLoss,
            rr,
        }),
        source: "fallback",
    }));
}


function buildScale({
    trade,
    setup,
    targets,
}) {
    const prices = [
        toNumber(trade?.entry_price),
        toNumber(trade?.stop_loss),
        toNumber(trade?.take_profit),
        toNumber(setup?.assessed_target_price),
        ...targets.map((target) => toNumber(target.price)),
        ...(setup?.zones || []).flatMap((zone) => [
            toNumber(zone.lower),
            toNumber(zone.upper),
            toNumber(zone.center),
        ]),
    ].filter((value) => value !== null);

    if (prices.length === 0) {
        return {
            min: 0,
            max: 1,
            range: 1,
        };
    }

    let min = Math.min(...prices);
    let max = Math.max(...prices);

    if (min === max) {
        min -= 1;
        max += 1;
    }

    const padding = Math.abs(max - min) * 0.08;

    min -= padding;
    max += padding;

    return {
        min,
        max,
        range: max - min,
    };
}


function positionPrice(price, scale) {
    const numeric = toNumber(price);

    if (numeric === null || scale.range <= 0) {
        return 0;
    }

    const value = ((numeric - scale.min) / scale.range) * 100;

    return Math.min(
        100,
        Math.max(
            0,
            value,
        ),
    );
}


function getZoneColor(zoneType) {
    if (zoneType === "resistance") {
        return "error";
    }

    if (zoneType === "support") {
        return "success";
    }

    return "default";
}


function getZoneLabel(zoneType) {
    if (zoneType === "resistance") {
        return "Resistance";
    }

    if (zoneType === "support") {
        return "Support";
    }

    return zoneType || "Zone";
}


function getTargetClearLabel(setup) {
    if (!setup) {
        return "Setup API не завантажено";
    }

    if (setup.assessed_target_clear) {
        return `TP 1:${setup.assessed_rr} clear`;
    }

    return `TP 1:${setup.assessed_rr} blocked`;
}


function getTargetClearColor(setup) {
    if (!setup) {
        return "default";
    }

    return setup.assessed_target_clear
        ? "success"
        : "warning";
}


function humanizeMtfLabel(value) {
    if (!value) {
        return "";
    }

    const spaced = String(value).replace(/_/g, " ");

    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}


function getMtfStatusChip(mtf) {
    const humanizedType = humanizeMtfLabel(mtf?.confirmation_type);

    if (mtf?.confirmation_type === "insufficient_data") {
        return {
            color: "default",
            label: "Insufficient data",
        };
    }

    if (mtf?.confirmed) {
        return {
            color: "success",
            label: humanizedType
                ? `Confirmed · ${humanizedType}`
                : "Confirmed",
        };
    }

    return {
        color: "warning",
        label: humanizedType
            ? `Not confirmed · ${humanizedType}`
            : "Not confirmed",
    };
}


function getMtfScoreDisplay(mtf) {
    const base = toNumber(mtf?.base_score);
    const delta = toNumber(mtf?.score_delta);
    const final = toNumber(mtf?.final_score);

    // A bonus is only ever shown when it actually changed the score.
    // applied=false (e.g. score already capped at 100) means the
    // bonus must not be described as applied, even if score_delta
    // itself is a positive number.
    const showBonus = (
        mtf?.applied === true
        && delta !== null
        && delta > 0
    );

    const capped = (
        mtf?.confirmed === true
        && mtf?.applied === false
        && delta !== null
        && delta > 0
        && base !== null
        && final !== null
        && base === final
    );

    return {
        base,
        delta,
        final,
        showBonus,
        capNote: capped ? "Score capped at 100" : null,
    };
}


function getMtfCandleLine(mtf) {
    const aligned = toNumber(mtf?.aligned_candle_count);

    if (aligned === null) {
        return null;
    }

    const raw = toNumber(mtf?.raw_candle_count);
    const discarded = toNumber(mtf?.discarded_candle_count);

    let line = raw === null
        ? `Aligned candles: ${aligned}`
        : `Aligned candles: ${aligned} of ${raw}`;

    if (discarded !== null && discarded > 0) {
        line += ` · Discarded: ${discarded}`;
    }

    return line;
}


function getMtfAnalyzedLine(mtf) {
    const analyzed = toNumber(mtf?.analyzed_candle_count);

    if (analyzed === null) {
        return null;
    }

    return `Analyzed for confirmation: ${analyzed}`;
}


function MTFConfirmationSummary({
    mtf,
}) {
    if (!mtf) {
        return null;
    }

    const title = mtf.entry_timeframe
        ? `${mtf.entry_timeframe} Confirmation`
        : "Entry Confirmation";

    const statusChip = getMtfStatusChip(mtf);
    const scoreDisplay = getMtfScoreDisplay(mtf);
    const candleLine = getMtfCandleLine(mtf);
    const analyzedLine = getMtfAnalyzedLine(mtf);
    const patternLabel = humanizeMtfLabel(mtf.expected_pattern);

    const hasScoreInfo = (
        scoreDisplay.base !== null
        || scoreDisplay.final !== null
        || scoreDisplay.showBonus
    );

    return (
        <Paper
            elevation={0}
            sx={{
                p: 1.5,
                border: 1,
                borderColor: "divider",
            }}
        >
            <Stack spacing={1}>
                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    sx={{
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                    }}
                >
                    <Typography
                        variant="subtitle2"
                        sx={{
                            fontWeight: "bold",
                        }}
                    >
                        {title}
                    </Typography>

                    <Chip
                        size="small"
                        color={statusChip.color}
                        label={statusChip.label}
                    />
                </Stack>

                {patternLabel && (
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        {patternLabel}
                    </Typography>
                )}

                {hasScoreInfo && (
                    <Stack
                        direction="row"
                        spacing={2}
                        useFlexGap
                        sx={{
                            alignItems: "baseline",
                            flexWrap: "wrap",
                        }}
                    >
                        {scoreDisplay.base !== null && (
                            <Typography variant="body2">
                                Base {scoreDisplay.base}
                            </Typography>
                        )}

                        {scoreDisplay.showBonus && (
                            <Typography
                                variant="body2"
                                color="success.main"
                            >
                                Bonus +{scoreDisplay.delta}
                            </Typography>
                        )}

                        {scoreDisplay.final !== null && (
                            <Typography
                                variant="body2"
                                sx={{
                                    fontWeight: "bold",
                                }}
                            >
                                Final {scoreDisplay.final}
                            </Typography>
                        )}
                    </Stack>
                )}

                {scoreDisplay.capNote && (
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        {scoreDisplay.capNote}
                    </Typography>
                )}

                {(candleLine || analyzedLine) && (
                    <Stack spacing={0.25}>
                        {candleLine && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {candleLine}
                            </Typography>
                        )}

                        {analyzedLine && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {analyzedLine}
                            </Typography>
                        )}
                    </Stack>
                )}
            </Stack>
        </Paper>
    );
}


function PriceMarker({
    label,
    price,
    scale,
    color = "primary",
}) {
    const left = positionPrice(
        price,
        scale,
    );

    return (
        <Box
            sx={{
                position: "absolute",
                left: `${left}%`,
                top: 0,
                bottom: 0,
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                pointerEvents: "none",
            }}
        >
            <Box
                sx={{
                    width: 2,
                    height: "100%",
                    bgcolor: `${color}.main`,
                    opacity: 0.85,
                }}
            />

            <Typography
                variant="caption"
                sx={{
                    mt: 0.5,
                    whiteSpace: "nowrap",
                    color: `${color}.main`,
                    fontWeight: "bold",
                }}
            >
                {label}
            </Typography>
        </Box>
    );
}


function ZoneBand({
    zone,
    scale,
}) {
    const left = positionPrice(
        zone.lower,
        scale,
    );

    const right = positionPrice(
        zone.upper,
        scale,
    );

    const width = Math.max(
        1,
        Math.abs(right - left),
    );

    const color = zone.zone_type === "resistance"
        ? "error.main"
        : "success.main";

    return (
        <Box
            sx={{
                position: "absolute",
                left: `${Math.min(left, right)}%`,
                width: `${width}%`,
                top: 8,
                bottom: 8,
                bgcolor: color,
                opacity: 0.16,
                borderRadius: 1,
            }}
        />
    );
}


function TargetCard({
    target,
    currentTakeProfit,
}) {
    const isCurrentTp = (
        toNumber(target.price) !== null
        && toNumber(currentTakeProfit) !== null
        && Math.abs(
            toNumber(target.price) - toNumber(currentTakeProfit),
        ) <= Math.abs(toNumber(currentTakeProfit)) * 0.0001
    );

    return (
        <Paper
            elevation={0}
            sx={{
                p: 1.5,
                border: 1,
                borderColor: isCurrentTp
                    ? "primary.main"
                    : "divider",
                minWidth: 130,
            }}
        >
            <Stack spacing={0.75}>
                <Stack
                    direction="row"
                    spacing={1}
                    sx={{
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        RR
                    </Typography>

                    <Chip
                        size="small"
                        label={`1:${target.rr}`}
                        color={isCurrentTp ? "primary" : "default"}
                    />
                </Stack>

                <Typography
                    variant="body1"
                    fontWeight="bold"
                >
                    {formatPrice(target.price)}
                </Typography>

                {isCurrentTp && (
                    <Typography
                        variant="caption"
                        color="primary.main"
                    >
                        Поточний TP
                    </Typography>
                )}
            </Stack>
        </Paper>
    );
}


function ZoneCard({
    zone,
    compact = false,
}) {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 1.5,
                border: 1,
                borderColor: "divider",
            }}
        >
            <Stack spacing={0.75}>
                <Stack
                    direction="row"
                    spacing={1}
                    useFlexGap
                    sx={{
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                    }}
                >
                    <Chip
                        size="small"
                        color={getZoneColor(zone.zone_type)}
                        label={getZoneLabel(zone.zone_type)}
                    />

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        touches: {zone.touches ?? "—"}
                    </Typography>
                </Stack>

                <Typography
                    variant={compact ? "body2" : "body1"}
                    fontWeight="bold"
                >
                    {formatPrice(zone.lower)}
                    {" — "}
                    {formatPrice(zone.upper)}
                </Typography>

                <Stack
                    direction="row"
                    spacing={2}
                    useFlexGap
                    sx={{
                        flexWrap: "wrap",
                    }}
                >
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Center: {formatPrice(zone.center)}
                    </Typography>

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Strength: {formatPercent(zone.strength)}
                    </Typography>

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Entry: {formatPercent(
                            zone.distance_to_entry_percent,
                        )}
                    </Typography>

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Target: {formatPercent(
                            zone.distance_to_target_percent,
                        )}
                    </Typography>
                </Stack>
            </Stack>
        </Paper>
    );
}


export default function SetupVisualization({
    trade,
    setup = null,
    setupError = "",
    setupLoading = false,
}) {
    if (!trade) {
        return null;
    }

    const entry = toNumber(trade.entry_price);
    const stopLoss = toNumber(trade.stop_loss);
    const currentTakeProfit = toNumber(trade.take_profit);
    const currentRR = calculateCurrentRR(trade);

    const targets = buildTargets({
        trade,
        setup,
    });

    const scale = buildScale({
        trade,
        setup,
        targets,
    });

    const blockingZones = setup?.blocking_zones || [];
    const zones = setup?.zones || [];

    const nearestZones = [...zones]
        .sort((left, right) => {
            const leftDistance = Math.abs(
                toNumber(left.distance_to_entry_percent) ?? 999999,
            );
            const rightDistance = Math.abs(
                toNumber(right.distance_to_entry_percent) ?? 999999,
            );

            return leftDistance - rightDistance;
        })
        .slice(0, 5);

    return (
        <Paper
            elevation={0}
            sx={{
                p: 2,
                border: 1,
                borderColor: "divider",
                bgcolor: "background.default",
            }}
        >
            <Stack spacing={2}>
                <Stack
                    direction={{
                        xs: "column",
                        sm: "row",
                    }}
                    spacing={1}
                    sx={{
                        justifyContent: "space-between",
                        alignItems: {
                            xs: "flex-start",
                            sm: "center",
                        },
                    }}
                >
                    <Box>
                        <Typography
                            variant="subtitle2"
                            fontWeight="bold"
                        >
                            Setup visualization
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            Entry / SL / TP, RR-цілі та support /
                            resistance зони.
                        </Typography>
                    </Box>

                    <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        sx={{
                            flexWrap: "wrap",
                        }}
                    >
                        <Chip
                            size="small"
                            label={
                                currentRR === null
                                    ? "Current RR: —"
                                    : `Current RR 1:${currentRR.toFixed(2)}`
                            }
                            color="primary"
                            variant="outlined"
                        />

                        <Chip
                            size="small"
                            label={getTargetClearLabel(setup)}
                            color={getTargetClearColor(setup)}
                        />
                    </Stack>
                </Stack>

                <MTFConfirmationSummary
                    mtf={trade.mtf}
                />

                {setupLoading && (
                    <Alert
                        severity="info"
                        icon={<CircularProgress size={18} />}
                    >
                        Завантажую setup-аналіз...
                    </Alert>
                )}

                {setupError && (
                    <Alert severity="warning">
                        Setup API недоступний для цієї угоди:
                        {" "}
                        {setupError}
                    </Alert>
                )}

                {setup?.summary && (
                    <Alert
                        severity={
                            setup.assessed_target_clear
                                ? "success"
                                : "warning"
                        }
                    >
                        {setup.summary}
                    </Alert>
                )}

                <Box>
                    <Box
                        sx={{
                            position: "relative",
                            height: 92,
                            borderRadius: 2,
                            border: 1,
                            borderColor: "divider",
                            overflow: "hidden",
                            bgcolor: "background.paper",
                        }}
                    >
                        {zones.map((zone, index) => (
                            <ZoneBand
                                key={`${zone.zone_type}-${zone.center}-${index}`}
                                zone={zone}
                                scale={scale}
                            />
                        ))}

                        <Box
                            sx={{
                                position: "absolute",
                                left: 0,
                                right: 0,
                                top: "50%",
                                height: 8,
                                transform: "translateY(-50%)",
                                bgcolor: "action.hover",
                            }}
                        />

                        <PriceMarker
                            label="SL"
                            price={stopLoss}
                            scale={scale}
                            color="error"
                        />

                        <PriceMarker
                            label="Entry"
                            price={entry}
                            scale={scale}
                            color="primary"
                        />

                        <PriceMarker
                            label="TP"
                            price={currentTakeProfit}
                            scale={scale}
                            color="success"
                        />

                        {setup?.assessed_target_price && (
                            <PriceMarker
                                label={`1:${setup.assessed_rr}`}
                                price={setup.assessed_target_price}
                                scale={scale}
                                color={
                                    setup.assessed_target_clear
                                        ? "success"
                                        : "warning"
                                }
                            />
                        )}
                    </Box>

                    <Stack
                        direction="row"
                        sx={{
                            justifyContent: "space-between",
                            mt: 1,
                        }}
                    >
                        <Typography
                            variant="caption"
                            color="text.secondary"
                        >
                            {formatPrice(scale.min)}
                        </Typography>

                        <Typography
                            variant="caption"
                            color="text.secondary"
                        >
                            {formatPrice(scale.max)}
                        </Typography>
                    </Stack>
                </Box>

                <Box>
                    <Typography
                        variant="subtitle2"
                        sx={{
                            mb: 1,
                        }}
                    >
                        RR targets
                    </Typography>

                    <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        sx={{
                            flexWrap: "wrap",
                        }}
                    >
                        {targets.map((target) => (
                            <TargetCard
                                key={`target-${target.rr}`}
                                target={target}
                                currentTakeProfit={currentTakeProfit}
                            />
                        ))}
                    </Stack>
                </Box>

                <Divider />

                <Box>
                    <Stack
                        direction="row"
                        spacing={1}
                        sx={{
                            alignItems: "center",
                            mb: 1,
                        }}
                    >
                        <Typography variant="subtitle2">
                            Blocking zones
                        </Typography>

                        <Chip
                            size="small"
                            label={blockingZones.length}
                            color={
                                blockingZones.length > 0
                                    ? "warning"
                                    : "success"
                            }
                        />
                    </Stack>

                    {blockingZones.length === 0 ? (
                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            Блокуючих зон для цілі 1:3 не знайдено.
                        </Typography>
                    ) : (
                        <Stack spacing={1}>
                            {blockingZones.map((zone, index) => (
                                <ZoneCard
                                    key={`blocking-${zone.center}-${index}`}
                                    zone={zone}
                                    compact
                                />
                            ))}
                        </Stack>
                    )}
                </Box>

                <Box>
                    <Stack
                        direction="row"
                        spacing={1}
                        sx={{
                            alignItems: "center",
                            mb: 1,
                        }}
                    >
                        <Typography variant="subtitle2">
                            Найближчі support / resistance
                        </Typography>

                        <Chip
                            size="small"
                            label={nearestZones.length}
                            variant="outlined"
                        />
                    </Stack>

                    {nearestZones.length === 0 ? (
                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            Зони поки не знайдені.
                        </Typography>
                    ) : (
                        <Stack spacing={1}>
                            {nearestZones.map((zone, index) => (
                                <ZoneCard
                                    key={`nearest-${zone.center}-${index}`}
                                    zone={zone}
                                    compact
                                />
                            ))}
                        </Stack>
                    )}
                </Box>
            </Stack>
        </Paper>
    );
}