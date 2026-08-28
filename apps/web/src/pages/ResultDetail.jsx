import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api/client.js";

export default function ResultDetail() {
  const { model, benchmark } = useParams();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState("metric");
  const [filter, setFilter] = useState("");
  const [deleting, setDeleting] = useState(false);

  const deleteResult = async () => {
    if (!window.confirm(`Delete the result for ${model} / ${benchmark}? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.deleteDetailedResult(model, benchmark, result.metadata.timestamp);
      window.location.href = "/";
    } catch (e) {
      setError(e.message);
      setDeleting(false);
    }
  };

  useEffect(() => {
    api.getDetailedResult(model, benchmark).then(setResult).catch((e) => setError(e.message));
  }, [model, benchmark]);

  if (error) return <div className="panel error-text">{error}</div>;
  if (!result) return <div className="panel">Loading...</div>;

  let entries = Object.entries(result.metrics || {});
  if (filter) {
    entries = entries.filter(([k]) => k.toLowerCase().includes(filter.toLowerCase()));
  }
  entries.sort((a, b) => {
    if (sortKey === "metric") return a[0].localeCompare(b[0]);
    const av = typeof a[1] === "number" ? a[1] : -Infinity;
    const bv = typeof b[1] === "number" ? b[1] : -Infinity;
    return bv - av;
  });

  return (
    <div>
      <Link to="/" style={{ color: "var(--muted)", fontSize: 13 }}>&larr; Back to dashboard</Link>
      <h1>{model}</h1>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p className="subtitle">Benchmark: {benchmark}</p>
        <button className="danger" onClick={deleteResult} disabled={deleting}>
          {deleting ? "Deleting..." : "Delete result"}
        </button>
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Run metadata</h2>
        <table>
          <tbody>
            <tr><th>Provider</th><td>{result.metadata.provider}</td></tr>
            <tr><th>Timestamp</th><td>{new Date(result.metadata.timestamp).toLocaleString()}</td></tr>
            <tr><th>Duration</th><td>{result.metadata.duration_seconds?.toFixed?.(1) ?? "-"} s</td></tr>
            <tr><th>Harness version</th><td>{result.metadata.harness_version || "-"}</td></tr>
            <tr><th>Git commit</th><td>{result.metadata.git_commit || "-"}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>All metrics</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <input placeholder="Search metrics..." value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 200 }} />
            <select value={sortKey} onChange={(e) => setSortKey(e.target.value)} style={{ width: 160 }}>
              <option value="metric">Sort by name</option>
              <option value="value">Sort by value</option>
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr><th>Metric</th><th>Value</th></tr>
          </thead>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td className="metric-value">{typeof value === "number" ? value.toFixed(4) : String(value)}</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={2} className="empty-cell">No metrics match your filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
