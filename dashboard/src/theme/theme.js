import { createTheme } from "@mui/material/styles";

const theme = createTheme({
    palette: {
        mode: "dark",

        primary: {
            main: "#3b82f6",
        },

        secondary: {
            main: "#10b981",
        },

        background: {
            default: "#0f172a",
            paper: "#1e293b",
        },
    },

    typography: {
        fontFamily: "Roboto, Arial, sans-serif",

        h5: {
            fontWeight: 700,
        },

        h6: {
            fontWeight: 600,
        },
    },

    shape: {
        borderRadius: 12,
    },
});

export default theme;