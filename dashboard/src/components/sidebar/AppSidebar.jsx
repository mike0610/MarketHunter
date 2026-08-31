import {
    Box,
    Drawer,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Toolbar,
    Typography,
} from "@mui/material";

import AccountBalanceIcon from "@mui/icons-material/AccountBalance";
import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import AssessmentIcon from "@mui/icons-material/Assessment";
import CandlestickChartIcon from "@mui/icons-material/CandlestickChart";
import DashboardIcon from "@mui/icons-material/Dashboard";
import SearchIcon from "@mui/icons-material/Search";
import SettingsIcon from "@mui/icons-material/Settings";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TimelineIcon from "@mui/icons-material/Timeline";

import { NavLink } from "react-router-dom";


const drawerWidth = 240;

const items = [
    { text: "Dashboard", icon: <DashboardIcon />, path: "/dashboard" },
    { text: "Scanner", icon: <SearchIcon />, path: "/scanner" },
    { text: "Signals", icon: <TimelineIcon />, path: "/signals" },
    { text: "Research", icon: <AnalyticsIcon />, path: "/research" },
    { text: "Active Trading", icon: <CandlestickChartIcon />, path: "/active-trading" },
    { text: "Portfolio", icon: <AccountBalanceWalletIcon />, path: "/portfolio" },
    { text: "Investments", icon: <AccountBalanceIcon />, path: "/investments" },
    { text: "Backtests", icon: <ShowChartIcon />, path: "/backtests" },
    { text: "Reports", icon: <AssessmentIcon />, path: "/reports" },
    { text: "Settings", icon: <SettingsIcon />, path: "/settings" },
];

function SidebarContent({ onNavigate }) {
    return (
        <Box sx={{ width: drawerWidth }}>
            <Toolbar>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    🏹 MarketHunter
                </Typography>
            </Toolbar>

            <List>
                {items.map((item) => (
                    <ListItemButton
                        key={item.text}
                        component={NavLink}
                        to={item.path}
                        onClick={onNavigate}
                        sx={{
                            "&.active": {
                                bgcolor: "action.selected",
                            },
                        }}
                    >
                        <ListItemIcon>{item.icon}</ListItemIcon>
                        <ListItemText primary={item.text} />
                    </ListItemButton>
                ))}
            </List>
        </Box>
    );
}

export default function AppSidebar({ mobileOpen = false, onMobileClose }) {
    return (
        <>
            <Drawer
                variant="temporary"
                open={mobileOpen}
                onClose={onMobileClose}
                ModalProps={{ keepMounted: true }}
                sx={{
                    display: { xs: "block", md: "none" },
                    "& .MuiDrawer-paper": {
                        width: drawerWidth,
                        boxSizing: "border-box",
                    },
                }}
            >
                <SidebarContent onNavigate={onMobileClose} />
            </Drawer>

            <Drawer
                variant="permanent"
                open
                sx={{
                    display: { xs: "none", md: "block" },
                    width: drawerWidth,
                    flexShrink: 0,
                    "& .MuiDrawer-paper": {
                        width: drawerWidth,
                        boxSizing: "border-box",
                    },
                }}
            >
                <SidebarContent />
            </Drawer>
        </>
    );
}
