import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [showMetadata, setShowMetadata] = useState(false);
  const [sort, setSort] = useState({ key: "model", direction: "asc" });
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
  const commonKeys = Array.from(new Set(models.flatMap((model) => benchmarks.flatMap((b) =>
    (matrix[model]?.[b]?.providers || []).flatMap((p) => Object.keys(p.metadata?.common || {})))))).sort();
  const hasValue = (value) => value !== undefined && value !== null && value !== "" &&
    !(typeof value === "object" && Object.keys(value).length === 0);
  const formatMetadata = (value, prefix = "") => {
    if (!hasValue(value)) return "";
    if (typeof value !== "object") return `${prefix}${value}`;
    return Object.entries(value).map(([key, item]) => formatMetadata(item, `${prefix}${key}: `)).filter(Boolean).join("\n");
  };
  const visibleCommonKeys = commonKeys.filter((key) => models.some((model) => benchmarks.some((b) =>
    (matrix[model]?.[b]?.providers || []).some((p) => hasValue(p.metadata?.common?.[key])))));
  const showExtraConf = models.some((model) => benchmarks.some((b) =>
    (matrix[model]?.[b]?.providers || []).some((p) => hasValue(p.metadata?.extra_conf))));
  const showResources = models.some((model) => benchmarks.some((b) =>
    (matrix[model]?.[b]?.providers || []).some((p) => hasValue(p.metadata?.resources))));

  const filteredModels = models.filter((m) =>
    m.toLowerCase().includes(search.toLowerCase())
  );

  const toggleSort = (key) => {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  const sortValue = (model, key) => {
    if (key === "model") return model;
    if (key === "metadata") return JSON.stringify(matrix[model]?.[benchmarks[0]]?.providers?.[0]?.metadata || {});
    const cell = matrix[model]?.[key];
    return showMetadata
      ? cell?.providers?.[0]?.value ?? null
      : cell?.value ?? null;
  };

  const sortedModels = [...filteredModels].sort((a, b) => {
    const left = sortValue(a, sort.key);
    const right = sortValue(b, sort.key);
    if (left === right) return 0;
    if (left === null || left === undefined || left === "") return 1;
    if (right === null || right === undefined || right === "") return -1;
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return sort.direction === "asc" ? comparison : -comparison;
  });

  const sortIndicator = (key) => sort.key !== key ? "" : sort.direction === "asc" ? "▲" : "▼";

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
        checked={showMetadata}
          onChange={(e) => setShowMetadata(e.target.checked)}
        />
        Show metadata
      </label>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th className="sortable-header" onClick={() => toggleSort("model")}>Model {sortIndicator("model")}</th>
              {showMetadata && <><th>Provider</th>{visibleCommonKeys.map((key) => <th key={key}>{key}</th>)}{showExtraConf && <th>extra_conf</th>}{showResources && <th>Resources</th>}</>}
              {benchmarks.map((b) => (
                <th key={b} className="sortable-header" onClick={() => toggleSort(b)}>{b} {sortIndicator(b)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedModels.flatMap((model) => {
              const allProviders = benchmarks.flatMap((bench) => matrix[model]?.[bench]?.providers || []);
              const providers = showMetadata
                ? [...new Map(allProviders.map((p) => [JSON.stringify({ provider: p.provider, metadata: p.metadata || {} }), p])).values()]
                : [null];
              const providerRows = showMetadata ? Math.max(1, providers.length) : 1;
              return Array.from({ length: providerRows }, (_, rowIndex) => (
              <tr key={`${model}-${rowIndex}`}>
                {rowIndex === 0 && <td rowSpan={providerRows}>{model}</td>}
                {showMetadata && (() => { const p = providers[rowIndex]; const common = p?.metadata?.common || {}; return <><td>{p?.provider || "-"}</td>{visibleCommonKeys.map((key) => <td key={key}>{common[key] ?? ""}</td>)}{showExtraConf && <td style={{ whiteSpace: "pre-wrap", textAlign: "left" }}>{formatMetadata(p?.metadata?.extra_conf)}</td>}{showResources && <td style={{ whiteSpace: "pre-wrap", textAlign: "left" }}>{formatMetadata(p?.metadata?.resources)}</td>}</>; })()}
                {benchmarks.map((bench) => {
                  const cell = matrix[model]?.[bench];
                  const score = showMetadata
                    ? cell?.providers?.find((p) => JSON.stringify({ provider: p.provider, metadata: p.metadata || {} }) === JSON.stringify({ provider: providers[rowIndex]?.provider, metadata: providers[rowIndex]?.metadata || {} }))
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
