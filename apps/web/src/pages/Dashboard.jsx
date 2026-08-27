import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [showProviders, setShowProviders] = useState(false);
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
      <label className="table-toggle">
        <input
          type="checkbox"
          checked={showProviders}
          onChange={(e) => setShowProviders(e.target.checked)}
        />
        Mostrar resultados por provider
      </label>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Model</th>
              {showProviders && <th>Provider</th>}
              {benchmarks.map((b) => (
                <th key={b}>{b}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredModels.flatMap((model) => {
              const providerRows = showProviders
                ? Math.max(1, ...benchmarks.map((bench) => matrix[model]?.[bench]?.providers?.length || 0))
                : 1;
              const providers = showProviders
                ? Array.from(new Set(benchmarks.flatMap((bench) => (matrix[model]?.[bench]?.providers || []).map((p) => p.provider)))).sort()
                : [null];
              return Array.from({ length: providerRows }, (_, rowIndex) => (
              <tr key={`${model}-${rowIndex}`}>
                {rowIndex === 0 && <td rowSpan={providerRows}>{model}</td>}
                {showProviders && <td>{providers[rowIndex] || "-"}</td>}
                {benchmarks.map((bench) => {
                  const cell = matrix[model]?.[bench];
                  const score = showProviders
                    ? cell?.providers?.find((p) => p.provider === providers[rowIndex])
                    : cell;
                  if (!score || score.value === null || score.value === undefined) {
                    return <td key={bench} className="empty-cell">-</td>;
                  }
                  return (
                    <td
                      key={bench}
                      className="score-cell"
                      onClick={() => navigate(`/results/${encodeURIComponent(model)}/${encodeURIComponent(bench)}`)}
                      title={`Primary metric: ${score.primary_metric}`}
                    >
                      {typeof score.value === "number" ? score.value.toFixed(4) : String(score.value)}
                    </td>
                  );
                })}
              </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
