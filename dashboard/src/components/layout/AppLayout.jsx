import { Box } from "@mui/material";

import AppSidebar from "../sidebar/AppSidebar";
import AppTopBar from "../topbar/AppTopBar";

export default function AppLayout({ children }) {

    return (

        <Box
            sx={{
                display: "flex",
                height: "100vh",
                bgcolor: "background.default",
            }}
        >

            <AppSidebar />

            <Box
                sx={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                }}
            >

                <AppTopBar />

                <Box
                    sx={{
                        flex: 1,
                        p: 3,
                        overflow: "auto",
                    }}
                >

                    {children}

                </Box>

            </Box>

        </Box>

    );

}