import { Activity, Clock, Zap, Percent, Repeat, Wifi } from 'lucide-react';

function MetricsPanel({ metrics }) {
  if (!metrics) return null;

  const cards = [
    {
      title: "Packet Delivery",
      value: `${(metrics.pdr || 0).toFixed(1)}%`,
      sub: `${metrics.packets_delivered || 0}/${metrics.packets_sent || 0} pkts`,
      colorClass: (metrics.pdr > 80) ? "accent-green" : "accent-warn",
      icon: <Percent size={14} />
    },
    {
      title: "First Node Death",
      value: metrics.fnd_step ? `Step ${metrics.fnd_step}` : "—",
      sub: "FND",
      colorClass: "accent-red",
      icon: <Activity size={14} />
    },
    {
      title: "Energy Variance",
      value: (metrics.energy_variance || 0).toFixed(1),
      sub: "lower = balanced",
      colorClass: "accent-blue",
      icon: <Zap size={14} />
    },
    {
      title: "Rerouting Events",
      value: metrics.rerouting_events || 0,
      sub: "path changes",
      colorClass: "accent-blue",
      icon: <Repeat size={14} />
    },
    {
      title: "Network Lifetime",
      value: `${(metrics.network_lifetime_s || 0).toFixed(0)}s`,
      sub: "uptime",
      colorClass: "accent-blue",
      icon: <Clock size={14} />
    },
    {
      title: "Throughput",
      value: (metrics.throughput_pps || 0).toFixed(2),
      sub: "pkts/sec",
      colorClass: "accent-green",
      icon: <Wifi size={14} />
    }
  ];

  return (
    <div className="metrics-grid">
      {cards.map((card, i) => (
        <div key={i} className={`metric-card ${card.colorClass}`}>
          <div className="metric-title" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {card.icon} {card.title}
          </div>
          <div className="metric-value">{card.value}</div>
          <div style={{ fontSize: '10px', color: '#64748B', marginTop: '4px' }}>{card.sub}</div>
        </div>
      ))}
    </div>
  );
}

export default MetricsPanel;
