import { Cloud, Server, Cpu, Database, Timer, RefreshCw, ShieldCheck, Navigation, GitBranch, FileStack } from 'lucide-react';

/**
 * CloudPanel — Firestore Cloud Sync panel.
 * ----------------------------------------
 * Rendered only when the ESP32 is operating in Gateway Mode.
 *
 * Reads the real `cloud` status block produced by the backend cloud_sync
 * service (Google Firestore mirror). If the backend hasn't reported a cloud
 * block (e.g. firebase-admin not installed), it falls back to derived counts
 * so the panel still renders meaningfully during a demo.
 */
function CloudPanel({ data, gateway }) {
  const cloud = data?.cloud || null;
  const nodes = Object.values(data?.nodes || {});

  // ── Connection state ──────────────────────────────────────────────────────
  const connected = cloud ? !!cloud.connected : false;
  const enabled = cloud ? !!cloud.enabled : false;
  const cloudStatus = cloud?.cloud_status || (enabled ? 'Reconnecting' : 'Disabled');
  const firestoreStatus = cloud?.firestore_status || 'unknown';
  const projectId = cloud?.project_id || 'wsn-el';
  const gatewayId = cloud?.gateway_id || gateway;

  // ── Record counts (real Firestore write counters) ─────────────────────────
  const counts = cloud?.counts || {};
  const fallbackTelemetry = nodes.reduce((s, n) => s + (n.packets_sent || 0), 0);
  const telemetryCount = counts.telemetry ?? fallbackTelemetry;
  const routingCount = counts.routing_events ?? 0;
  const chCount = counts.cluster_head_events ?? 0;
  const rlCount = counts.rl_decisions ?? 0;
  const gatewayLogCount = counts.gateway_logs ?? 0;

  const lastSync = cloud?.last_sync
    ? new Date(cloud.last_sync * 1000).toLocaleTimeString('en-US', { hour12: false })
    : '—';

  const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : n);

  const rows = [
    {
      label: 'Cloud Status',
      value: cloudStatus,
      icon: <Cloud size={14} />,
      tone: connected ? 'good' : enabled ? 'warn' : 'muted',
      dot: connected,
    },
    {
      label: 'Firestore Connection',
      value: firestoreStatus.replace('_', ' '),
      icon: <Database size={14} />,
      tone: connected ? 'good' : 'warn',
    },
    {
      label: 'Project / Gateway',
      value: `${projectId} · ${gatewayId}`,
      icon: <Server size={14} />,
      tone: 'blue',
    },
    {
      label: 'Total Telemetry Records',
      value: fmt(telemetryCount),
      icon: <FileStack size={14} />,
      tone: 'blue',
    },
    {
      label: 'Total Routing Events',
      value: fmt(routingCount),
      icon: <Navigation size={14} />,
      tone: 'blue',
    },
    {
      label: 'Cluster Head Events',
      value: fmt(chCount),
      icon: <GitBranch size={14} />,
      tone: 'blue',
    },
    {
      label: 'Total RL Decisions',
      value: fmt(rlCount),
      icon: <Cpu size={14} />,
      tone: 'blue',
    },
    {
      label: 'Total Gateway Logs',
      value: fmt(gatewayLogCount),
      icon: <RefreshCw size={14} />,
      tone: 'blue',
    },
    {
      label: 'Last Synchronization',
      value: lastSync,
      icon: <Timer size={14} />,
      tone: 'muted',
    },
  ];

  const toneColor = {
    good: '#10B981',
    warn: '#F59E0B',
    blue: '#3B82F6',
    muted: '#94A3B8',
  };

  return (
    <div className="cloud-grid">
      {rows.map((row, i) => (
        <div key={i} className="cloud-stat">
          <div className="cloud-stat-label">
            <span style={{ color: toneColor[row.tone] }}>{row.icon}</span>
            {row.label}
          </div>
          <div className="cloud-stat-value" style={{ color: toneColor[row.tone] }}>
            {row.dot && <span className="cloud-dot" />}
            {row.value}
          </div>
        </div>
      ))}

      {cloud?.last_error && !connected && (
        <div className="cloud-error">
          ⚠ {cloud.last_error}
        </div>
      )}

      <div className="cloud-flow">
        <div className="cloud-flow-title">
          <ShieldCheck size={13} /> Edge → Cloud Data Flow (Google Firestore)
        </div>
        <div className="cloud-flow-chain">
          {['Sensor Nodes', 'Cluster Head', `${gatewayId} (Gateway)`, 'MQTT', 'Backend', 'Google Firestore'].map((stage, i, arr) => (
            <span key={i} className="cloud-flow-stage">
              {stage}
              {i < arr.length - 1 && <span className="cloud-flow-arrow">↓</span>}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default CloudPanel;
