import React from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import ExperimentBuilder from "./pages/ExperimentBuilder.jsx";
import LiveMonitoring from "./pages/LiveMonitoring.jsx";
import ResultDetail from "./pages/ResultDetail.jsx";
import ExperimentsList from "./pages/ExperimentsList.jsx";

export default function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">LLM Benchmarking Framework</div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/experiments">Experiments</NavLink>
          <NavLink to="/experiments/new">New Experiment</NavLink>
          <NavLink to="/monitoring">Live Monitoring</NavLink>
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/results/:model/:benchmark" element={<ResultDetail />} />
          <Route path="/experiments" element={<ExperimentsList />} />
          <Route path="/experiments/new" element={<ExperimentBuilder />} />
          <Route path="/monitoring" element={<LiveMonitoring />} />
          <Route path="/monitoring/:experimentId" element={<LiveMonitoring />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
