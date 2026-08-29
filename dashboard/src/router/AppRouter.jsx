import {
    Navigate,
    Route,
    Routes,
} from "react-router-dom";

import AppLayout from "../components/layout/AppLayout";

import ActiveTrading from "../pages/ActiveTrading";
import Backtests from "../pages/Backtests";
import Dashboard from "../pages/Dashboard";
import Investments from "../pages/Investments";
import Portfolio from "../pages/Portfolio";
import Reports from "../pages/Reports";
import Research from "../pages/Research";
import Scanner from "../pages/Scanner";
import Settings from "../pages/Settings";
import Signals from "../pages/Signals";


export default function AppRouter() {
    return (
        <AppLayout>
            <Routes>
                <Route
                    path="/"
                    element={
                        <Navigate
                            to="/dashboard"
                            replace
                        />
                    }
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
                    path="/research"
                    element={<Research />}
                />

                <Route
                    path="/active-trading"
                    element={<ActiveTrading />}
                />

                <Route
                    path="/portfolio"
                    element={<Portfolio />}
                />

                <Route
                    path="/investments"
                    element={<Investments />}
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
