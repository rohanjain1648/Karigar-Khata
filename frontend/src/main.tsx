import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Home from "./pages/Home";
import JewellerLayout from "./pages/jeweller/Layout";
import Dashboard from "./pages/jeweller/Dashboard";
import IssueGold from "./pages/jeweller/IssueGold";
import Jobs from "./pages/jeweller/Jobs";
import JobDetail from "./pages/jeweller/JobDetail";
import Karigars from "./pages/jeweller/Karigars";
import KarigarAccount from "./pages/jeweller/KarigarAccount";
import Settlements from "./pages/jeweller/Settlements";
import Compliance from "./pages/jeweller/Compliance";
import Ledger from "./pages/jeweller/Ledger";
import KarigarApp from "./pages/karigar/KarigarApp";
import Track from "./pages/Track";
import Demo from "./pages/Demo";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/k" element={<KarigarApp />} />
        <Route path="/track/:code" element={<Track />} />
        <Route path="/j" element={<JewellerLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="issue" element={<IssueGold />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="karigars" element={<Karigars />} />
          <Route path="karigars/:id" element={<KarigarAccount />} />
          <Route path="settlements" element={<Settlements />} />
          <Route path="compliance" element={<Compliance />} />
          <Route path="ledger" element={<Ledger />} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
