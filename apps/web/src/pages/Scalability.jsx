import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";

const formatSeconds = (value) => value === null || value === undefined ? "-" : `${(value * 1000).toFixed(0)} ms`;
const formatRate = (value) => value === null || value === undefined ? "-" : `${value.toFixed(2)} tok/s`;
const formatMetadata = (value, prefix = "") => {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value !== "object") return `${prefix}${value}`;
  return Object.entries(value).flatMap(([key, item]) =>
    formatMetadata(item, `${prefix}${key}: `).split("\n")
  ).join("\n");
};

function Metadata({ value, indent = 0 }) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  return Object.entries(value).map(([key, item]) => (
    <div key={`${indent}-${key}`} style={{ paddingLeft: `${indent * 2}ch` }}>
      <strong>{key}:</strong>{typeof item === "object" && item !== null ? <Metadata value={item} indent={indent + 1} /> : ` ${item}`}
    </div>
  ));
}

function MetricHelp() {
  return <details className="panel metric-help">
    <summary>What does each metric mean?</summary>
    <dl>
      <dt>TTFT p50</dt><dd>Median time until the first token is received. It represents the typical response start time.</dd>
      <dt>Latency p95</dt><dd>Total time until the response is complete at the 95th percentile. It helps identify slow requests under load.</dd>
      <dt>Aggregate tok/s</dt><dd>Output tokens per second across all requests at that concurrency level. It measures the total serving capacity of the server.</dd>
      <dt>Decode tok/s</dt><dd>Mean tokens per second for each individual response, measured from its first token to its last. It represents generation speed after the response starts.</dd>
      <dt>Errors</dt><dd>Failed requests relative to the total, displayed as failed/total.</dd>
      <dt>users</dt><dd>Number of requests kept active simultaneously at that load level.</dd>
    </dl>
    <p className="metric-note">p50 is the median; p95 means that 95% of requests completed within that time or less. An asterisk (*) indicates that the token count was estimated because the provider did not report actual usage.</p>
  </details>;
}

export default function Scalability() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState({ key: "model", direction: "asc" });

  useEffect(() => {
    api.getScalabilityResults().then(setData).catch((e) => setError(e.message));
  }, []);

  const { users, rows: unsortedRows } = useMemo(() => {
    const results = data?.results || [];
    const levels = [...new Set(results.map((result) => result.users))].sort((a, b) => a - b);
    const grouped = new Map();
    results.forEach((result) => {
      const signature = JSON.stringify(result.metadata || {});
      const key = `${result.model}\u0000${result.provider}\u0000${signature}`;
      if (!grouped.has(key)) grouped.set(key, { model: result.model, provider: result.provider, metadata: result.metadata || {}, values: {} });
      grouped.get(key).values[result.users] = result;
    });
    return { users: levels, rows: [...grouped.values()].sort((a, b) => a.model.localeCompare(b.model) || a.provider.localeCompare(b.provider)) };
  }, [data]);

  const toggleSort = (key) => setSort((current) => ({
    key,
    direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
  }));
  const indicator = (key) => sort.key === key ? (sort.direction === "asc" ? "▲" : "▼") : "";
  const metricValue = (row, key) => {
    if (key === "model") return row.model;
    if (key === "provider") return row.provider;
    const [level, metric] = key.split(":");
    return row.values[level]?.metrics?.[metric] ?? null;
  };
  const rows = [...unsortedRows].sort((a, b) => {
    const left = metricValue(a, sort.key);
    const right = metricValue(b, sort.key);
    if (left === right) return a.model.localeCompare(b.model) || a.provider.localeCompare(b.provider);
    if (left === null || left === undefined) return 1;
    if (right === null || right === undefined) return -1;
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return sort.direction === "asc" ? comparison : -comparison;
  });

  if (error) return <div className="panel error-text">Failed to load scalability results: {error}</div>;
  if (!data) return <div className="panel">Loading scalability results...</div>;
  if (!rows.length) return <div><h1>Scalability</h1><p className="subtitle">Concurrent streaming performance by model and provider.</p><MetricHelp /><div className="panel">No scalability tests yet. Add a <code>scalability</code> section to an experiment YAML and run it.</div></div>;

  // Keep model groups together when rows are sorted by a provider metric.
  const groupedRows = [...new Set(rows.map((row) => row.model))].flatMap((model) => rows.filter((row) => row.model === model));
  let previousModel = null;
  const modelCounts = groupedRows.reduce((counts, row) => ({ ...counts, [row.model]: (counts[row.model] || 0) + 1 }), {});
  return (
    <div>
      <h1>Scalability</h1>
      <p className="subtitle">Streaming performance under concurrent load. TTFT is time to first token; output throughput may be estimated when the provider does not report token usage.</p>
      <MetricHelp />
      <div className="panel" style={{ overflowX: "auto" }}>
        <table className="scalability-table">
          <thead>
            <tr><th rowSpan="2" className="sortable-header" onClick={() => toggleSort("model")}>Model {indicator("model")}</th><th rowSpan="2">Provider</th><th rowSpan="2">Metadata</th>{users.map((level) => <th key={level} colSpan="5" className="group-header">{level} users</th>)}</tr>
            <tr>{users.flatMap((level) => [<th key={`${level}-ttft`} className="sortable-header" onClick={() => toggleSort(`${level}:ttft_p50_seconds`)}>TTFT p50 {indicator(`${level}:ttft_p50_seconds`)}</th>, <th key={`${level}-latency`} className="sortable-header" onClick={() => toggleSort(`${level}:latency_p95_seconds`)}>Latency p95 {indicator(`${level}:latency_p95_seconds`)}</th>, <th key={`${level}-rate`} className="sortable-header" onClick={() => toggleSort(`${level}:output_tokens_per_second`)}>Aggregate tok/s {indicator(`${level}:output_tokens_per_second`)}</th>, <th key={`${level}-perceived`} className="sortable-header" onClick={() => toggleSort(`${level}:perceived_tokens_per_second_mean`)}>Decode tok/s {indicator(`${level}:perceived_tokens_per_second_mean`)}</th>, <th key={`${level}-errors`} className="sortable-header" onClick={() => toggleSort(`${level}:error_rate`)}>Errors {indicator(`${level}:error_rate`)}</th>])}</tr>
          </thead>
          <tbody>
            {groupedRows.map((row) => {
              const showModel = row.model !== previousModel;
              previousModel = row.model;
              return <tr key={`${row.model}-${row.provider}-${JSON.stringify(row.metadata)}`}>
                {showModel && <td rowSpan={modelCounts[row.model]}>{row.model}</td>}
                <td>{row.provider}</td><td title={formatMetadata(row.metadata)} style={{ textAlign: "left" }}><Metadata value={{ ...(row.metadata.common || {}), ...(row.metadata.extra_conf || {}), ...(row.metadata.resources || {}) }} /></td>
                {users.flatMap((level) => {
                  const result = row.values[level];
                  const metrics = result?.metrics;
                  return [
                    <td key={`${level}-ttft`}>{formatSeconds(metrics?.ttft_p50_seconds)}</td>,
                    <td key={`${level}-latency`}>{formatSeconds(metrics?.latency_p95_seconds)}</td>,
                    <td key={`${level}-rate`}>{formatRate(metrics?.output_tokens_per_second)}{metrics?.tokens_estimated ? "*" : ""}</td>,
                    <td key={`${level}-perceived`}>{formatRate(metrics?.perceived_tokens_per_second_mean)}{metrics?.tokens_estimated ? "*" : ""}</td>,
                    <td key={`${level}-errors`}>{metrics ? `${metrics.failed_requests}/${metrics.requests}` : "-"}</td>,
                  ];
                })}
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      <p className="subtitle">* Token count estimated from generated text because the provider did not return completion-token usage.</p>
    </div>
  );
}
