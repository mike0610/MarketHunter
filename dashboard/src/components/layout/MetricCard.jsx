import {
    Box,
    Paper,
    Typography,
} from "@mui/material";


/**
 * Small KPI tile: label + big value + optional caption underneath.
 * Mirrors the (previously page-local, now shared) MetricCard style
 * from Research.jsx so every page uses the same visual language.
 */
export default function MetricCard({
    label,
    value,
    caption,
    valueColor,
}) {
    return (
        <Paper
            variant="outlined"
            sx={{
                p: 2,
                borderRadius: 3,
                minWidth: 0,
                bgcolor: "rgba(255,255,255,0.02)",
                height: "100%",
            }}
        >
            <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                    wordBreak: "break-word",
                }}
            >
                {label}
            </Typography>

            <Typography
                variant="h5"
                fontWeight={700}
                color={valueColor}
                sx={{
                    mt: 1,
                    wordBreak: "break-word",
                }}
            >
                {value}
            </Typography>

            {caption && (
                <Box sx={{ mt: 0.5 }}>
                    <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                            wordBreak: "break-word",
                        }}
                    >
                        {caption}
                    </Typography>
                </Box>
            )}
        </Paper>
    );
}
