import {

    AppBar,
    Toolbar,
    Typography,
    Chip,
    Stack,

} from "@mui/material";

export default function AppTopBar() {

    return (

        <AppBar
            position="static"
            elevation={1}
        >

            <Toolbar>

                <Typography
                    variant="h6"
                    sx={{
                        flexGrow: 1,
                    }}
                >

                    MarketHunter Terminal

                </Typography>

                <Stack
                    direction="row"
                    spacing={2}
                >

                    <Chip
                        label="FastAPI Connected"
                        color="success"
                    />

                    <Chip
                        label="Scanner Ready"
                        color="primary"
                    />

                </Stack>

            </Toolbar>

        </AppBar>

    );

}