import { Routes, Route, Navigate } from "react-router-dom";

import AppLayout from "../components/layout/AppLayout";

import Dashboard from "../pages/Dashboard";
import Scanner from "../pages/Scanner";
import Signals from "../pages/Signals";
import Portfolio from "../pages/Portfolio";
import Backtests from "../pages/Backtests";
import Reports from "../pages/Reports";
import Settings from "../pages/Settings";

export default function AppRouter() {
    return (
        <AppLayout>
            <Routes>
                <Route
                    path="/"
                    element={<Navigate to="/dashboard" replace />}
                />

                <Route
                    path="/dashboard"
                    element={<Dashboard />}
                />

                <Route
                    path="/scanner"
                    element={<Scanner />}
                />

                <Route
                    path="/signals"
                    element={<Signals />}
                />

                <Route
                    path="/portfolio"
                    element={<Portfolio />}
                />

                <Route
                    path="/backtests"
                    element={<Backtests />}
                />

                <Route
                    path="/reports"
                    element={<Reports />}
                />

                <Route
                    path="/settings"
                    element={<Settings />}
                />
            </Routes>
        </AppLayout>
    );
}