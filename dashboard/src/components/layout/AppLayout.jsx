import { useState } from "react";

import { Box } from "@mui/material";

import AppSidebar from "../sidebar/AppSidebar";
import AppTopBar from "../topbar/AppTopBar";

export default function AppLayout({ children }) {
    const [mobileNavOpen, setMobileNavOpen] = useState(false);

    return (
        <Box
            sx={{
                display: "flex",
                minHeight: "100vh",
                bgcolor: "background.default",
            }}
        >
            <AppSidebar
                mobileOpen={mobileNavOpen}
                onMobileClose={() => setMobileNavOpen(false)}
            />

            <Box
                sx={{
                    flex: 1,
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <AppTopBar onMenuClick={() => setMobileNavOpen(true)} />

                <Box
                    component="main"
                    sx={{
                        flex: 1,
                        minWidth: 0,
                        width: "100%",
                        p: { xs: 2, sm: 3 },
                        overflowX: "hidden",
                        overflowY: "auto",
                    }}
                >
                    {children}
                </Box>
            </Box>
        </Box>
    );
}
