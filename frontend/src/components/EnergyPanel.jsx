import { Plug, Wifi } from 'lucide-react';

function EnergyPanel({ nodes }) {
  if (!nodes || nodes.length === 0) return null;

  // Separate SINK from sensor nodes
  const sinkNode  = nodes.find(n => (n.node_id || n.id) === 'SINK');
  const sensorNodes = nodes.filter(n => (n.node_id || n.id) !== 'SINK');

  // Sort sensor nodes by energy ascending (lowest first = most at-risk)
  const sortedNodes = [...sensorNodes].sort((a, b) => {
    const eA = a.alive ? (a.energy || 0) : 0;
    const eB = b.alive ? (b.energy || 0) : 0;
    return eA - eB;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>

      {/* SINK special card */}
      {sinkNode && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          background: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px', padding: '8px 12px',
        }}>
          <Plug size={16} color="#EF4444" />
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#EF4444' }}>SINK (Base Station)</div>
            <div style={{ fontSize: '11px', color: '#94A3B8' }}>Mains-powered · Always alive · Final destination</div>
          </div>
          <div style={{ marginLeft: 'auto', fontSize: '11px', color: '#10B981', fontWeight: 700 }}>
            ∞ Power
          </div>
        </div>
      )}

      {/* Sensor node energy bars */}
      <div className="energy-list">
        {sortedNodes.map((node, index) => {
          const nId   = node.node_id || node.id || index;
          const energy = node.alive ? (node.energy || 0) : 0;
          const nType  = node.node_type || node.type || 'virtual';

          let barColor = '#475569'; // dead
          if (node.alive) {
            if (energy > 66)      barColor = '#10B981'; // green
            else if (energy > 33) barColor = '#F59E0B'; // amber
            else                  barColor = '#EF4444'; // red
          }

          // Border colour by node type
          let typeLabel = '';
          let typeBadgeColor = '#475569';
          if (nType === 'real')    { typeLabel = 'REAL'; typeBadgeColor = '#F59E0B'; }
          else if (nType === 'wokwi') { typeLabel = 'WOKWI'; typeBadgeColor = '#3B82F6'; }

          return (
            <div key={nId} className="energy-item">
              <div style={{ width: '90px', display: 'flex', flexDirection: 'column' }}>
                <span className="energy-label" style={{
                  color: node.alive ? '#E2E8F0' : '#475569',
                  fontSize: '12px', fontFamily: 'monospace',
                }}>
                  {!node.alive && '💀 '}{nId}
                </span>
                {typeLabel && (
                  <span style={{
                    fontSize: '9px', color: typeBadgeColor,
                    fontWeight: 700, letterSpacing: '0.05em',
                  }}>{typeLabel}</span>
                )}
              </div>
              <div className="energy-bar-container">
                <div
                  className="energy-bar-fill"
                  style={{ width: `${energy}%`, backgroundColor: barColor }}
                />
              </div>
              <div className="energy-value" style={{ color: barColor }}>
                {node.alive ? `${energy.toFixed(1)}%` : 'DEAD'}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default EnergyPanel;
