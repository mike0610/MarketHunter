import { NavLink } from "react-router-dom";

import "../../styles/sidebar.css";

export default function Sidebar() {

    return (

        <aside className="sidebar">

            <h2 className="logo">

                MarketHunter

            </h2>

            <nav>

                <NavLink to="/dashboard">

                    Dashboard

                </NavLink>

                <NavLink to="/scanner">

                    Scanner

                </NavLink>

                <NavLink to="/signals">

                    Signals

                </NavLink>

                <NavLink to="/portfolio">

                    Portfolio

                </NavLink>

                <NavLink to="/backtests">

                    Backtests

                </NavLink>

                <NavLink to="/reports">

                    Reports

                </NavLink>

                <NavLink to="/settings">

                    Settings

                </NavLink>

            </nav>

        </aside>

    );

}