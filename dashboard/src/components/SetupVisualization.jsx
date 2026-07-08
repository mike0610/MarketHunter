import {
    Alert,
    Box,
    Chip,
    Divider,
    Paper,
    Stack,
    Typography,
} from "@mui/material";


function formatPrice(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return new Intl.NumberFormat(
        "uk-UA",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: 8,
        },
    ).format(value);
}


function formatPercent(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return `${Number(value).toFixed(2)}%`;
}


function calculateSetup(trade) {
    const direction = String(
        trade?.direction || "",
    ).toUpperCase();

    const entry = Number(trade?.entry_price);
    const stopLoss = Number(trade?.stop_loss);
    const takeProfit = Number(trade?.take_profit);

    if (
        !Number.isFinite(entry)
        || !Number.isFinite(stopLoss)
        || !Number.isFinite(takeProfit)
        || entry <= 0
    ) {
        return null;
    }

    const risk = direction === "LONG"
        ? entry - stopLoss
        : stopLoss - entry;

    if (risk <= 0) {
        return null;
    }

    const currentReward = direction === "LONG"
        ? takeProfit - entry
        : entry - takeProfit;

    const currentRiskReward = currentReward / risk;

    const scenarios = [1, 2, 3].map((rr) => {
        const targetPrice = direction === "LONG"
            ? entry + risk * rr
            : entry - risk * rr;

        const movePercent = Math.abs(
            (targetPrice - entry) / entry,
        ) * 100;

        const isCurrentTarget = (
            Math.abs(targetPrice - takeProfit)
            <= Math.max(Math.abs(takeProfit) * 0.000001, 0.00000001)
        );

        return {
            rr,
            targetPrice,
            movePercent,
            isCurrentTarget,
        };
    });

    const riskPercent = Math.abs(
        (entry - stopLoss) / entry,
    ) * 100;

    return {
        direction,
        entry,
        stopLoss,
        takeProfit,
        risk,
        riskPercent,
        currentRiskReward,
        scenarios,
    };
}


function PriceLine({
    label,
    price,
    chip,
}) {
    return (
        <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            spacing={2}
        >
            <Stack
                direction="row"
                spacing={1}
                alignItems="center"
            >
                <Typography
                    variant="body2"
                    fontWeight="bold"
                >
                    {label}
                </Typography>

                {chip}
            </Stack>

            <Typography
                variant="body2"
                fontWeight="bold"
            >
                {formatPrice(price)}
            </Typography>
        </Stack>
    );
}


function ScenarioCard({
    scenario,
}) {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 1.5,
                flex: "1 1 140px",
                border: 1,
                borderColor: scenario.isCurrentTarget
                    ? "success.main"
                    : "divider",
                bgcolor: scenario.isCurrentTarget
                    ? "success.main"
                    : "background.paper",
            }}
        >
            <Stack spacing={0.75}>
                <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                >
                    <Typography
                        variant="body2"
                        fontWeight="bold"
                    >
                        1:{scenario.rr}
                    </Typography>

                    {scenario.isCurrentTarget && (
                        <Chip
                            size="small"
                            label="поточний TP"
                            color="success"
                            variant="outlined"
                        />
                    )}
                </Stack>

                <Typography variant="body2">
                    TP: {formatPrice(scenario.targetPrice)}
                </Typography>

                <Typography
                    variant="caption"
                    color="text.secondary"
                >
                    Рух від Entry: {formatPercent(scenario.movePercent)}
                </Typography>
            </Stack>
        </Paper>
    );
}


export default function SetupVisualization({
    trade,
}) {
    const setup = calculateSetup(trade);

    if (!setup) {
        return (
            <Alert severity="warning">
                Неможливо побудувати RR-сетап:
                некоректні Entry / SL / TP.
            </Alert>
        );
    }

    const isLong = setup.direction === "LONG";

    const topLabel = isLong
        ? "Take Profit"
        : "Stop Loss";

    const topPrice = isLong
        ? setup.takeProfit
        : setup.stopLoss;

    const bottomLabel = isLong
        ? "Stop Loss"
        : "Take Profit";

    const bottomPrice = isLong
        ? setup.stopLoss
        : setup.takeProfit;

    const topZoneLabel = isLong
        ? "Зона прибутку"
        : "Зона ризику";

    const bottomZoneLabel = isLong
        ? "Зона ризику"
        : "Зона прибутку";

    const topZoneColor = isLong
        ? "success.main"
        : "error.main";

    const bottomZoneColor = isLong
        ? "error.main"
        : "success.main";

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
                    justifyContent="space-between"
                    alignItems={{
                        xs: "flex-start",
                        sm: "center",
                    }}
                    spacing={1}
                >
                    <Box>
                        <Typography
                            variant="subtitle2"
                            fontWeight="bold"
                        >
                            Візуалізація сетапу
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                                mt: 0.5,
                            }}
                        >
                            Entry / SL / TP та RR-сценарії 1:1, 1:2, 1:3.
                        </Typography>
                    </Box>

                    <Chip
                        label={`Поточний RR: 1:${setup.currentRiskReward.toFixed(2)}`}
                        color="info"
                        variant="outlined"
                    />
                </Stack>

                <Stack spacing={1.25}>
                    <PriceLine
                        label={topLabel}
                        price={topPrice}
                        chip={
                            <Chip
                                size="small"
                                label={topZoneLabel}
                                color={isLong ? "success" : "error"}
                                variant="outlined"
                            />
                        }
                    />

                    <Box
                        sx={{
                            height: 46,
                            borderRadius: 1,
                            bgcolor: topZoneColor,
                            opacity: 0.22,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            border: 1,
                            borderColor: topZoneColor,
                        }}
                    >
                        <Typography
                            variant="caption"
                            fontWeight="bold"
                        >
                            {topZoneLabel}
                        </Typography>
                    </Box>

                    <Divider>
                        <Chip
                            label={`Entry ${formatPrice(setup.entry)}`}
                            size="small"
                        />
                    </Divider>

                    <Box
                        sx={{
                            height: 46,
                            borderRadius: 1,
                            bgcolor: bottomZoneColor,
                            opacity: 0.22,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            border: 1,
                            borderColor: bottomZoneColor,
                        }}
                    >
                        <Typography
                            variant="caption"
                            fontWeight="bold"
                        >
                            {bottomZoneLabel}
                        </Typography>
                    </Box>

                    <PriceLine
                        label={bottomLabel}
                        price={bottomPrice}
                        chip={
                            <Chip
                                size="small"
                                label={bottomZoneLabel}
                                color={isLong ? "error" : "success"}
                                variant="outlined"
                            />
                        }
                    />
                </Stack>

                <Divider />

                <Stack
                    direction="row"
                    flexWrap="wrap"
                    gap={1.5}
                >
                    {setup.scenarios.map((scenario) => (
                        <ScenarioCard
                            key={scenario.rr}
                            scenario={scenario}
                        />
                    ))}
                </Stack>

                <Typography
                    variant="caption"
                    color="text.secondary"
                >
                    Ризик до SL:
                    {" "}
                    {formatPercent(setup.riskPercent)}
                    {" "}
                    від Entry. Далі сюди додамо support/resistance zones,
                    щоб бачити, чи TP не впирається в сильну зону.
                </Typography>
            </Stack>
        </Paper>
    );
}