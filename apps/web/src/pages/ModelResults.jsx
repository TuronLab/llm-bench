import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";

function PrettyData({ value, indent = 0 }) {
  if (value === null || value === undefined || value === "") return <span className="empty-cell">-</span>;
  if (typeof value !== "object") return <span>{typeof value === "number" ? value.toLocaleString() : String(value)}</span>;
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== "" && (typeof item !== "object" || Object.keys(item).length));
  return <div>{entries.map(([key, item]) => <div key={`${indent}-${key}`} className="data-line" style={{ paddingLeft: `${indent * 2}ch` }}><strong>{key}:</strong>{typeof item === "object" && item !== null ? <PrettyData value={item} indent={indent + 1} /> : <span> {String(item)}</span>}</div>)}</div>;
}
const pretty = (value) => <div className="metadata-block"><PrettyData value={value || {}} /></div>;
const MetricTable = ({ value }) => <table className="metric-card-table"><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>{Object.entries(value || {}).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([key, item]) => <tr key={key}><td><strong>{key}</strong></td><td>{typeof item === "object" ? <PrettyData value={item} /> : String(item)}</td></tr>)}</tbody></table>;
const Card = ({ title, children, onDelete }) => <div className="result-card"><div className="result-card-header"><h3>{title}</h3><button className="danger" onClick={onDelete}>Delete</button></div>{children}</div>;
export default function ModelResults() {
  const { model } = useParams(); const [benchmarks, setBenchmarks] = useState(null); const [loads, setLoads] = useState(null); const [error, setError] = useState(null);
  const refresh = () => Promise.all([api.getModelResults(model).catch(() => ({ results: [] })), api.getScalabilityResults()]).then(([b, s]) => { setBenchmarks(b.results || []); setLoads((s.results || []).filter((r) => r.model === model)); }).catch((e) => setError(e.message));
  useEffect(() => { refresh(); }, [model]);
  const groups = useMemo(() => { const map = new Map(); [...(benchmarks || []).map((r) => ({ type: "benchmarks", provider: r.metadata.provider, config: r.metadata.metadata, result: r })), ...(loads || []).map((r) => ({ type: "loads", provider: r.provider, config: r.metadata, result: r }))].forEach((x) => { const key = `${x.provider}\0${JSON.stringify(x.config || {})}`; if (!map.has(key)) map.set(key, { provider: x.provider, config: x.config || {}, benchmarks: [], loads: [] }); map.get(key)[x.type].push(x.result); }); return [...map.values()]; }, [benchmarks, loads]);
  const remove = async (message, action) => { if (window.confirm(message)) { await action(); refresh(); } };
  if (error) return <div className="panel error-text">{error}</div>; if (!benchmarks || !loads) return <div className="panel">Loading...</div>;
  return <div><Link className="model-link" to="/">&larr; Back to dashboard</Link><h1>{model}</h1>{groups.map((g) => <section className="model-group" key={`${g.provider}-${JSON.stringify(g.config)}`}><h2>Provider: {g.provider}</h2><div className="panel configuration"><strong>Configuration</strong>{pretty(g.config)}<div className="result-cards">{g.benchmarks.map((r) => <Card key={`b-${r.metadata.timestamp}`} title={`Benchmark: ${r.metadata.benchmark}`} onDelete={() => remove("Delete this benchmark result?", () => api.deleteDetailedResult(model, r.metadata.benchmark, r.metadata.timestamp))}><MetricTable value={r.metrics} /></Card>)}{g.loads.map((r) => <Card key={`l-${r.timestamp}`} title={`Load testing: ${r.users} users`} onDelete={() => remove("Delete this load-test result?", () => api.deleteScalabilityResult(r))}><MetricTable value={r.metrics} /></Card>)}</div></div></section>)}{!groups.length && <div className="panel">No results for this model.</div>}</div>;
}
