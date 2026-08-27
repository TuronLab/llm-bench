import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";

const formatSeconds = (value) => value === null || value === undefined ? "-" : `${(value * 1000).toFixed(0)} ms`;
const formatRate = (value) => value === null || value === undefined ? "-" : `${value.toFixed(2)} tok/s`;

function MetricHelp() {
  return <details className="panel metric-help" open>
    <summary>¿Qué significa cada métrica?</summary>
    <dl>
      <dt>TTFT p50</dt><dd>Tiempo mediano hasta recibir el primer token. Representa el comportamiento típico de inicio de respuesta.</dd>
      <dt>Latency p95</dt><dd>Tiempo total hasta completar la respuesta en el percentil 95. Ayuda a detectar las peticiones lentas bajo carga.</dd>
      <dt>Output total</dt><dd>Tokens por segundo agregados entre todas las peticiones del nivel de concurrencia. Mide la capacidad total del servidor.</dd>
      <dt>Output/user</dt><dd>Media de tokens por segundo de cada respuesta individual, desde su primer token hasta el último. Es la velocidad percibida por cada usuario.</dd>
      <dt>Errors</dt><dd>Peticiones fallidas respecto al total, mostradas como fallos/total.</dd>
      <dt>users</dt><dd>Número de peticiones que se mantienen simultáneamente activas en ese nivel de carga.</dd>
    </dl>
    <p className="metric-note">p50 es la mediana; p95 indica que el 95% de las peticiones terminó en ese tiempo o menos. Un asterisco (*) indica que el número de tokens fue estimado porque el provider no informó del uso real.</p>
  </details>;
}

export default function Scalability() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getScalabilityResults().then(setData).catch((e) => setError(e.message));
  }, []);

  const { users, rows } = useMemo(() => {
    const results = data?.results || [];
    const levels = [...new Set(results.map((result) => result.users))].sort((a, b) => a - b);
    const grouped = new Map();
    results.forEach((result) => {
      const key = `${result.model}\u0000${result.provider}`;
      if (!grouped.has(key)) grouped.set(key, { model: result.model, provider: result.provider, values: {} });
      grouped.get(key).values[result.users] = result;
    });
    return { users: levels, rows: [...grouped.values()].sort((a, b) => a.model.localeCompare(b.model) || a.provider.localeCompare(b.provider)) };
  }, [data]);

  if (error) return <div className="panel error-text">Failed to load scalability results: {error}</div>;
  if (!data) return <div className="panel">Loading scalability results...</div>;
  if (!rows.length) return <div><h1>Scalability</h1><p className="subtitle">Concurrent streaming performance by model and provider.</p><MetricHelp /><div className="panel">No scalability tests yet. Add a <code>scalability</code> section to an experiment YAML and run it.</div></div>;

  let previousModel = null;
  const modelCounts = rows.reduce((counts, row) => ({ ...counts, [row.model]: (counts[row.model] || 0) + 1 }), {});
  return (
    <div>
      <h1>Scalability</h1>
      <p className="subtitle">Streaming performance under concurrent load. TTFT is time to first token; output throughput may be estimated when the provider does not report token usage.</p>
      <MetricHelp />
      <div className="panel" style={{ overflowX: "auto" }}>
        <table className="scalability-table">
          <thead>
            <tr><th rowSpan="2">Model</th><th rowSpan="2">Provider</th>{users.map((level) => <th key={level} colSpan="5" className="group-header">{level} users</th>)}</tr>
            <tr>{users.flatMap((level) => [<th key={`${level}-ttft`}>TTFT p50</th>, <th key={`${level}-latency`}>Latency p95</th>, <th key={`${level}-rate`}>Output total</th>, <th key={`${level}-perceived`}>Output/user</th>, <th key={`${level}-errors`}>Errors</th>])}</tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const showModel = row.model !== previousModel;
              previousModel = row.model;
              return <tr key={`${row.model}-${row.provider}`}>
                {showModel && <td rowSpan={modelCounts[row.model]}>{row.model}</td>}
                <td title={JSON.stringify(Object.values(row.values)[0]?.provider_options || {}, null, 2)}>{row.provider}</td>
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
