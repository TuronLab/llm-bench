import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.getResultsMatrix().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="panel error-text">Failed to load results: {error}</div>;
  if (!data) return <div className="panel">Loading dashboard...</div>;

  const { models, matrix } = data;
  const benchmarks = Array.from(
    new Set(Object.values(matrix).flatMap((row) => Object.keys(row)))
  ).sort();

  const filteredModels = models.filter((m) =>
    m.toLowerCase().includes(search.toLowerCase())
  );

  if (models.length === 0) {
    return (
      <div>
        <h1>Dashboard</h1>
        <p className="subtitle">Model x benchmark score matrix</p>
        <div className="panel">
          No results yet. Create and run an experiment to populate the dashboard.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="subtitle">Primary score per model x benchmark. Click a cell for full metrics.</p>
      <input
        placeholder="Filter models..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ maxWidth: 280, marginBottom: 16 }}
      />
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Model</th>
              {benchmarks.map((b) => (
                <th key={b}>{b}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredModels.map((model) => (
              <tr key={model}>
                <td>{model}</td>
                {benchmarks.map((bench) => {
                  const cell = matrix[model]?.[bench];
                  if (!cell || cell.value === null || cell.value === undefined) {
                    return <td key={bench} className="empty-cell">-</td>;
                  }
                  return (
                    <td
                      key={bench}
                      className="score-cell"
                      onClick={() => navigate(`/results/${encodeURIComponent(model)}/${encodeURIComponent(bench)}`)}
                      title={`Primary metric: ${cell.primary_metric}`}
                    >
                      {typeof cell.value === "number" ? cell.value.toFixed(4) : String(cell.value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
