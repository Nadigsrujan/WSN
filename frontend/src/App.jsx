import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Activity, Radio, Cpu, Network, Zap, GitCommit, Navigation, ScrollText } from 'lucide-react';
import TopologyGraph from './components/TopologyGraph';
import MetricsPanel from './components/MetricsPanel';
import EnergyPanel from './components/EnergyPanel';
import RlPanel from './components/RlPanel';
import RoutingTablePanel from './components/RoutingTablePanel';
import EventLogPanel from './components/EventLogPanel';

const API_URL = 'http://localhost:8001/api/state';

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const response = await axios.get(API_URL);
      setData(response.data);
      setError(null);
    } catch (err) {
      console.error("Error fetching data:", err);
      setError("Unable to connect to WSN Backend. Ensure run_backend.py and run_api.py are running.");
    }
  }, []);

  useEffect(() => {
    fetchData(); // Initial fetch
    const interval = setInterval(fetchData, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  if (error && !data) {
    return (
      <div className="loader">
        <Radio size={48} className="text-red-500" />
        <h2>Connection Error</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="loader">
        <Activity size={48} className="animate-pulse" />
        <h2>Waiting for WSN Backend...</h2>
      </div>
    );
  }

  const { graph, current_path, alt_path, metrics, rl, nodes, newly_dead, step, routing_table, event_log } = data;
  const nodesList = Object.values(nodes || {});
  const aliveCount = nodesList.filter(n => n.alive).length;

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <Network color="#3B82F6" />
          <h1>RL-Assisted WSN Dashboard</h1>
        </div>
        <div className="header-status">
          <div className="status-indicator live"></div>
          <span>LIVE • Step {step} • {aliveCount}/{nodesList.length} Nodes Alive</span>
        </div>
      </header>

      <div className="main-content">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <h2>Active Route</h2>
            {current_path && current_path.length > 0 ? (
              <div className="route-path-vertical">
                {current_path.map((node, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: i === current_path.length - 1 ? 0 : '8px' }}>
                    <GitCommit size={16} color={i === 0 ? '#3B82F6' : i === current_path.length - 1 ? '#10B981' : '#94A3B8'} />
                    <span style={{ fontFamily: 'monospace', color: '#E2E8F0' }}>{node}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: '#94A3B8', fontSize: '14px' }}>No active route.</p>
            )}
          </div>

          {/* Alternate Route */}
          {alt_path && alt_path.length > 0 && (
            <div className="sidebar-section">
              <h2>Alternate Route</h2>
              <div className="route-path-vertical">
                {alt_path.map((node, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: i === alt_path.length - 1 ? 0 : '8px' }}>
                    <GitCommit size={16} color="#8B5CF6" />
                    <span style={{ fontFamily: 'monospace', color: '#94A3B8' }}>{node}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Clusters Status */}
          {data.clusters && data.clusters.length > 0 && (
            <div className="sidebar-section">
              <h2>Clusters</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {data.clusters.map((c, i) => (
                  <div key={i} style={{ padding: '8px', background: '#1E293B', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <strong style={{ color: '#E2E8F0', fontSize: '13px' }}>Cluster {c.cluster_id}</strong>
                      <span style={{ color: '#FBBF24', fontSize: '12px', fontWeight: 'bold' }}>{c.ch_id || 'No CH'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94A3B8' }}>
                      <span>Members: {c.member_count}</span>
                      <span>Avg Energy: {c.avg_energy}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <div className="sidebar-section">
            <h2>Legend</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, borderRadius: '50%', background: '#10B981'}}></div> High Energy (&gt;66%)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, borderRadius: '50%', background: '#F59E0B'}}></div> Medium Energy</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, borderRadius: '50%', background: '#EF4444'}}></div> Low Energy (&lt;33%)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, borderRadius: '50%', background: '#475569'}}></div> Dead Node</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, background: '#F59E0B', clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)'}}></div> ESP32 (Real HW)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><div style={{width: 12, height: 12, background: '#EF4444', transform: 'rotate(45deg)'}}></div> SINK (Base Station)</div>
            </div>
          </div>
        </aside>

        {/* Main Dashboard Area */}
        <main className="dashboard-area">
          {current_path && current_path.length > 0 && (
            <div className="route-display">
              <Zap size={20} />
              <span>Packet routed: {current_path.join(' → ')}</span>
            </div>
          )}

          <div className="top-panels">
            {/* Topology Graph */}
            <div className="panel">
              <div className="panel-header">
                <Network size={18} /> Topology Map
              </div>
              <div className="panel-content no-padding">
                <TopologyGraph graphData={graph} currentPath={current_path} altPath={alt_path || []} nodesMap={nodes} />
              </div>
            </div>

            {/* Metrics */}
            <div className="panel">
              <div className="panel-header">
                <Activity size={18} /> Performance KPIs
              </div>
              <div className="panel-content">
                <MetricsPanel metrics={metrics} />
              </div>
            </div>
          </div>

          <div className="middle-panels">
            {/* Energy Levels */}
            <div className="panel">
              <div className="panel-header">
                <Cpu size={18} /> Node Energy Status
              </div>
              <div className="panel-content">
                <EnergyPanel nodes={nodesList} />
              </div>
            </div>

            {/* Routing Table */}
            <div className="panel">
              <div className="panel-header">
                <Navigation size={18} /> Routing Table
              </div>
              <div className="panel-content no-padding">
                <RoutingTablePanel routingTable={routing_table || {}} />
              </div>
            </div>
          </div>

          <div className="bottom-panels">
            {/* RL Agent Stats */}
            <div className="panel">
              <div className="panel-header">
                <Activity size={18} /> Q-Learning Agent
              </div>
              <div className="panel-content">
                <RlPanel rlState={rl} />
              </div>
            </div>

            {/* Event Log */}
            <div className="panel">
              <div className="panel-header">
                <ScrollText size={18} /> Event Log
              </div>
              <div className="panel-content no-padding">
                <EventLogPanel events={event_log || []} />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
