import {
    Box,
    Button,
    CircularProgress,
    Stack,
    Typography,
} from "@mui/material";

import RefreshIcon from "@mui/icons-material/Refresh";


/**
 * Consistent page header used across all dashboard pages: title,
 * optional subtitle, optional refresh button. Mirrors the header
 * pattern already established in Research.jsx so every page shares
 * the same visual language.
 */
export default function PageHeader({
    title,
    subtitle,
    onRefresh,
    refreshing = false,
    actions = null,
}) {
    return (
        <Stack
            direction={{
                xs: "column",
                md: "row",
            }}
            justifyContent="space-between"
            alignItems={{
                xs: "flex-start",
                md: "center",
            }}
            spacing={2}
            sx={{
                width: "100%",
                mb: 3,
            }}
        >
            <Box sx={{ minWidth: 0 }}>
                <Typography
                    variant="h3"
                    fontWeight={700}
                >
                    {title}
                </Typography>

                {subtitle && (
                    <Typography
                        variant="body1"
                        fontWeight={400}
                        color="text.secondary"
                        sx={{
                            mt: 1,
                            wordBreak: "break-word",
                        }}
                    >
                        {subtitle}
                    </Typography>
                )}
            </Box>

            <Stack
                direction="row"
                spacing={1.5}
                sx={{
                    width: {
                        xs: "100%",
                        md: "auto",
                    },
                }}
            >
                {actions}

                {onRefresh && (
                    <Button
                        variant="contained"
                        size="medium"
                        startIcon={
                            refreshing
                                ? (
                                    <CircularProgress
                                        size={18}
                                        color="inherit"
                                    />
                                )
                                : <RefreshIcon />
                        }
                        onClick={onRefresh}
                        disabled={refreshing}
                        sx={{
                            minWidth: {
                                xs: "100%",
                                sm: 150,
                            },
                            height: 44,
                            px: 2.5,
                            borderRadius: 3,
                        }}
                    >
                        Оновити
                    </Button>
                )}
            </Stack>
        </Stack>
    );
}
