import { useState, useEffect, useRef } from 'react';

const statusIcon = (status) => {
  switch (status) {
    case 'congested':  return '⚠️';
    case 'rerouted':   return '🔄';
    case 'ch_change':  return '⚡';
    default:           return '✅';
  }
};

const statusColor = (status) => {
  switch (status) {
    case 'congested':  return '#F59E0B';
    case 'rerouted':   return '#8B5CF6';
    case 'ch_change':  return '#facc15';
    default:           return '#10B981';
  }
};

function RoutingTablePanel({ routingTable, nodes }) {
  if (!routingTable) return null;

  // Build a lookup: node_id → { cluster_id, is_ch }
  const nodeInfo = {};
  if (nodes) {
    nodes.forEach(n => {
      nodeInfo[n.node_id || n.id] = {
        cluster_id: n.cluster_id ?? '—',
        is_ch: n.is_ch || false,
      };
    });
  }

  // Track previous values to flash changed rows
  const prevRef = useRef({});
  const [flashRows, setFlashRows] = useState({});

  useEffect(() => {
    const prev = prevRef.current;
    const newFlash = {};
    Object.entries(routingTable).forEach(([node, info]) => {
      const prevInfo = prev[node];
      if (!prevInfo) return;
      const nextHop  = typeof info === 'object' ? info.next_hop : info;
      const status   = typeof info === 'object' ? info.status : 'active';
      if (prevInfo.next_hop !== nextHop || prevInfo.status !== status) {
        newFlash[node] = true;
      }
    });

    if (Object.keys(newFlash).length > 0) {
      setFlashRows(newFlash);
      setTimeout(() => setFlashRows({}), 1200);
    }

    // Update previous ref
    prevRef.current = {};
    Object.entries(routingTable).forEach(([node, info]) => {
      prevRef.current[node] = {
        next_hop: typeof info === 'object' ? info.next_hop : info,
        status:   typeof info === 'object' ? info.status : 'active',
      };
    });
  }, [routingTable]);

  const entries = Object.entries(routingTable).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="table-container">
      <table className="data-table">
        <thead>
          <tr>
            <th>Node</th>
            <th>Cluster</th>
            <th>Role</th>
            <th>Next Hop</th>
            <th>Alt Hop</th>
            <th>Hops</th>
            <th>Cost</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {entries.length > 0 ? (
            entries.map(([node, info]) => {
              const nextHop  = typeof info === 'object' ? info.next_hop  : info;
              const altHop   = typeof info === 'object' ? info.alt_hop   : '—';
              const cost     = typeof info === 'object' ? info.cost       : '—';
              const altCost  = typeof info === 'object' ? info.alt_cost   : '—';
              const status   = typeof info === 'object' ? info.status     : 'active';
              const hopCount = typeof info === 'object' ? info.hop_count  : '—';
              const ni       = nodeInfo[node] || {};
              const isFlash  = !!flashRows[node];

              return (
                <tr key={node} style={{
                  backgroundColor: isFlash
                    ? 'rgba(250, 204, 21, 0.12)'
                    : status === 'congested'
                      ? 'rgba(245, 158, 11, 0.05)'
                      : 'transparent',
                  transition: 'background-color 0.4s ease',
                }}>
                  <td style={{ color: '#E2E8F0', fontWeight: 500, fontFamily: 'monospace' }}>
                    {node}
                  </td>
                  <td style={{ color: '#64748B', textAlign: 'center' }}>
                    {ni.cluster_id !== undefined ? ni.cluster_id + 1 : '—'}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {ni.is_ch
                      ? <span style={{ color: '#facc15', fontWeight: 700, fontSize: 13 }}>★ CH</span>
                      : <span style={{ color: '#475569', fontSize: 12 }}>node</span>
                    }
                  </td>
                  <td style={{ color: '#3B82F6', fontFamily: 'monospace' }}>{nextHop}</td>
                  <td style={{ color: '#6366f1', fontFamily: 'monospace' }}>{altHop}</td>
                  <td style={{ color: '#94A3B8', textAlign: 'center' }}>{hopCount}</td>
                  <td style={{ color: '#94A3B8' }}>{cost}</td>
                  <td style={{ color: statusColor(status), fontSize: '13px' }}>
                    {statusIcon(status)} {status}
                  </td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td colSpan="8" style={{ textAlign: 'center', color: '#94A3B8', padding: '20px' }}>
                No active routes
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default RoutingTablePanel;
