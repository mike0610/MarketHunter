import React from "react";
import ReactDOM from "react-dom/client";

import { BrowserRouter } from "react-router-dom";

import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

import "@fontsource/roboto";

import App from "./App";
import theme from "./theme/theme";

ReactDOM.createRoot(document.getElementById("root")).render(

    <React.StrictMode>

        <ThemeProvider theme={theme}>

            <CssBaseline />

            <BrowserRouter>

                <App />

            </BrowserRouter>

        </ThemeProvider>

    </React.StrictMode>

);