import {
    Drawer,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Toolbar,
    Typography,
} from "@mui/material";

import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import AssessmentIcon from "@mui/icons-material/Assessment";
import DashboardIcon from "@mui/icons-material/Dashboard";
import SearchIcon from "@mui/icons-material/Search";
import SettingsIcon from "@mui/icons-material/Settings";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TimelineIcon from "@mui/icons-material/Timeline";

import { NavLink } from "react-router-dom";


const drawerWidth = 240;

const items = [
    {
        text: "Dashboard",
        icon: <DashboardIcon />,
        path: "/dashboard",
    },
    {
        text: "Scanner",
        icon: <SearchIcon />,
        path: "/scanner",
    },
    {
        text: "Signals",
        icon: <TimelineIcon />,
        path: "/signals",
    },
    {
        text: "Research",
        icon: <AnalyticsIcon />,
        path: "/research",
    },
    {
        text: "Portfolio",
        icon: <AccountBalanceWalletIcon />,
        path: "/portfolio",
    },
    {
        text: "Backtests",
        icon: <ShowChartIcon />,
        path: "/backtests",
    },
    {
        text: "Reports",
        icon: <AssessmentIcon />,
        path: "/reports",
    },
    {
        text: "Settings",
        icon: <SettingsIcon />,
        path: "/settings",
    },
];


export default function AppSidebar() {
    return (
        <Drawer
            variant="permanent"
            sx={{
                width: drawerWidth,
                flexShrink: 0,

                "& .MuiDrawer-paper": {
                    width: drawerWidth,
                    boxSizing: "border-box",
                },
            }}
        >
            <Toolbar>
                <Typography
                    variant="h6"
                    fontWeight="bold"
                >
                    🏹 MarketHunter
                </Typography>
            </Toolbar>

            <List>
                {items.map((item) => (
                    <ListItemButton
                        key={item.text}
                        component={NavLink}
                        to={item.path}
                        sx={{
                            "&.active": {
                                bgcolor: "action.selected",
                            },
                        }}
                    >
                        <ListItemIcon>
                            {item.icon}
                        </ListItemIcon>

                        <ListItemText
                            primary={item.text}
                        />
                    </ListItemButton>
                ))}
            </List>
        </Drawer>
    );
}