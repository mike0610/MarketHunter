import Sidebar from "../sidebar/Sidebar";
import TopBar from "../topbar/TopBar";

import "../../styles/layout.css";

export default function Layout({ children }) {

    return (

        <div className="layout">

            <Sidebar />

            <div className="layout-main">

                <TopBar />

                <main className="layout-content">

                    {children}

                </main>

            </div>

        </div>

    );

}