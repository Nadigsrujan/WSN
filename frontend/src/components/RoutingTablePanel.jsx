import { Navigation, ArrowRight } from 'lucide-react';

function RoutingTablePanel({ routingTable }) {
  if (!routingTable) return null;

  const entries = Object.entries(routingTable).sort((a, b) => a[0].localeCompare(b[0]));

  const statusIcon = (status) => {
    switch (status) {
      case 'congested': return '⚠️';
      case 'rerouted':  return '🔄';
      default:          return '✅';
    }
  };

  const statusColor = (status) => {
    switch (status) {
      case 'congested': return '#F59E0B';
      case 'rerouted':  return '#8B5CF6';
      default:          return '#10B981';
    }
  };

  return (
    <div className="table-container">
      <table className="data-table">
        <thead>
          <tr>
            <th>Node</th>
            <th>Next Hop</th>
            <th>Alt Hop</th>
            <th>Cost</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {entries.length > 0 ? (
            entries.map(([node, info]) => {
              const nextHop = typeof info === 'object' ? info.next_hop : info;
              const altHop = typeof info === 'object' ? info.alt_hop : '—';
              const cost = typeof info === 'object' ? info.cost : '—';
              const status = typeof info === 'object' ? info.status : 'active';

              return (
                <tr key={node} style={{
                  backgroundColor: status === 'congested' ? 'rgba(245, 158, 11, 0.05)' : 'transparent',
                }}>
                  <td style={{ color: '#E2E8F0', fontWeight: 500 }}>{node}</td>
                  <td style={{ color: '#3B82F6' }}>{nextHop}</td>
                  <td style={{ color: '#64748B' }}>{altHop}</td>
                  <td style={{ color: '#94A3B8' }}>{cost}</td>
                  <td style={{ color: statusColor(status), fontSize: '13px' }}>
                    {statusIcon(status)} {status}
                  </td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td colSpan="5" style={{ textAlign: 'center', color: '#94A3B8' }}>
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
