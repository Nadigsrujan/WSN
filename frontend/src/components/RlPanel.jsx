import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LineChart, Line, ReferenceLine
} from 'recharts';
import { Brain, Activity, Target, Zap, Radio, BarChart2 } from 'lucide-react';

// Weight metadata — what each weight means technically
const WEIGHT_META = {
  w1: {
    label: 'Energy (w1)',
    description: 'Penalises low-battery next-hop nodes. High w1 = battery-aware routing.',
    color: '#10B981',
    formula: 'w1 × (1 / Ev)',
  },
  w2: {
    label: 'Distance (w2)',
    description: 'Penalises geographically distant hops. High w2 = prefer close neighbours.',
    color: '#3B82F6',
    formula: 'w2 × d_uv',
  },
  w3: {
    label: 'Link Quality (w3)',
    description: 'Penalises weak RSSI / high ETX links. High w3 = prefer reliable links.',
    color: '#8B5CF6',
    formula: 'w3 × (1 / LQ_uv)',
  },
  w4: {
    label: 'Traffic Load (w4)',
    description: 'Penalises congested relay nodes. High w4 = avoid busy nodes.',
    color: '#F59E0B',
    formula: 'w4 × Lv',
  },
};

const ACTION_LABELS = {
  boost_energy:   { label: 'Boost Energy Weight', icon: '⚡', color: '#10B981' },
  boost_distance: { label: 'Boost Distance Weight', icon: '📍', color: '#3B82F6' },
  boost_lq:       { label: 'Boost Link Quality', icon: '📶', color: '#8B5CF6' },
  boost_load:     { label: 'Boost Load Penalty', icon: '🔄', color: '#F59E0B' },
  keep:           { label: 'Hold Current Weights', icon: '🔒', color: '#94A3B8' },
  '—':            { label: 'Initialising…', icon: '…', color: '#475569' },
};

const STATE_LABELS = ['Energy Level', 'RSSI Level', 'Load Level', 'Network Health'];

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const w = payload[0].payload;
    const meta = WEIGHT_META[w.key] || {};
    return (
      <div style={{
        background: '#0B0F19', border: '1px solid #2A3143', borderRadius: '8px',
        padding: '12px', fontSize: '12px', maxWidth: '220px',
      }}>
        <div style={{ color: '#fff', fontWeight: 600, marginBottom: '6px' }}>{meta.label}</div>
        <div style={{ color: '#94A3B8', marginBottom: '8px' }}>{meta.description}</div>
        <div style={{
          background: '#151A25', padding: '6px 8px', borderRadius: '4px',
          fontFamily: 'monospace', color: '#60A5FA', fontSize: '11px'
        }}>
          Cost component: {meta.formula}
        </div>
        <div style={{ marginTop: '8px', color: '#10B981', fontWeight: 600 }}>
          Current value: {(w.value * 100).toFixed(1)}%
        </div>
      </div>
    );
  }
  return null;
};

function RlPanel({ rlState }) {
  if (!rlState || !rlState.weights) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#475569', gap: '8px' }}>
        <Brain size={24} /> Waiting for RL data...
      </div>
    );
  }

  const { weights, epsilon, step, recent_rewards, last_action, last_state } = rlState;

  // Build data for weight bars
  const weightData = ['w1', 'w2', 'w3', 'w4'].map(key => ({
    key,
    name: WEIGHT_META[key].label,
    value: weights[key] || 0,
    fill: WEIGHT_META[key].color,
  }));

  // Reward history for line chart
  const rewardData = (recent_rewards || []).map((r, i) => ({ i, reward: r }));
  const avgReward = rewardData.length
    ? (rewardData.reduce((a, b) => a + b.reward, 0) / rewardData.length).toFixed(2)
    : 0;

  const actionMeta = ACTION_LABELS[last_action] || ACTION_LABELS['—'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflow: 'auto', height: '100%' }}>

      {/* Top stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
        <div style={{ background: '#1C2230', padding: '10px', borderRadius: '8px', borderLeft: '3px solid #F59E0B' }}>
          <div style={{ fontSize: '10px', color: '#94A3B8', marginBottom: '2px' }}>Exploration (ε)</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#F59E0B', fontFamily: 'monospace' }}>
            {(epsilon * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '10px', color: '#475569', marginTop: '2px' }}>
            {epsilon > 0.15 ? 'Exploring' : epsilon > 0.06 ? 'Transitioning' : 'Exploiting'}
          </div>
        </div>
        <div style={{ background: '#1C2230', padding: '10px', borderRadius: '8px', borderLeft: '3px solid #8B5CF6' }}>
          <div style={{ fontSize: '10px', color: '#94A3B8', marginBottom: '2px' }}>RL Steps</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#8B5CF6', fontFamily: 'monospace' }}>{step}</div>
          <div style={{ fontSize: '10px', color: '#475569', marginTop: '2px' }}>Q-table updates</div>
        </div>
        <div style={{ background: '#1C2230', padding: '10px', borderRadius: '8px', borderLeft: '3px solid #10B981' }}>
          <div style={{ fontSize: '10px', color: '#94A3B8', marginBottom: '2px' }}>Avg Reward</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: avgReward >= 0 ? '#10B981' : '#EF4444', fontFamily: 'monospace' }}>
            {avgReward}
          </div>
          <div style={{ fontSize: '10px', color: '#475569', marginTop: '2px' }}>last {rewardData.length} steps</div>
        </div>
      </div>

      {/* Last action taken */}
      <div style={{
        background: '#1C2230', border: `1px solid ${actionMeta.color}44`, borderRadius: '8px',
        padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px'
      }}>
        <span style={{ fontSize: '20px' }}>{actionMeta.icon}</span>
        <div>
          <div style={{ fontSize: '10px', color: '#94A3B8' }}>Last Agent Action</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: actionMeta.color }}>{actionMeta.label}</div>
        </div>
        {last_state && last_state.length > 0 && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '6px' }}>
            {last_state.map((s, i) => (
              <div key={i} style={{
                background: '#0B0F19', borderRadius: '4px', padding: '4px 6px',
                fontSize: '10px', color: '#94A3B8', textAlign: 'center'
              }}>
                <div style={{ color: '#E2E8F0', fontWeight: 600, fontSize: '11px' }}>{s}</div>
                <div>{STATE_LABELS[i] ? STATE_LABELS[i].split(' ')[0] : ''}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cost function display */}
      <div style={{ background: '#1C2230', borderRadius: '8px', padding: '10px 14px' }}>
        <div style={{ fontSize: '10px', color: '#94A3B8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
          <BarChart2 size={12} /> ROUTING COST FUNCTION
        </div>
        <div style={{
          fontFamily: 'monospace', fontSize: '12px', color: '#60A5FA',
          background: '#0B0F19', padding: '8px 10px', borderRadius: '4px',
          letterSpacing: '0.02em'
        }}>
          Cost(u,v) ={' '}
          <span style={{ color: '#10B981' }}>w1</span>/Ev +{' '}
          <span style={{ color: '#3B82F6' }}>w2</span>·d_uv +{' '}
          <span style={{ color: '#8B5CF6' }}>w3</span>/LQ +{' '}
          <span style={{ color: '#F59E0B' }}>w4</span>·Lv
        </div>
      </div>

      {/* Weight bars — the main feature */}
      <div>
        <div style={{ fontSize: '11px', color: '#94A3B8', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Target size={12} /> ROUTING WEIGHT DISTRIBUTION <span style={{ color: '#475569', marginLeft: '4px' }}>(hover for details)</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {weightData.map((w) => {
            const pct = (w.value * 100).toFixed(1);
            const meta = WEIGHT_META[w.key];
            return (
              <div key={w.key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px' }}>
                  <span style={{ fontSize: '11px', color: '#E2E8F0' }}>{meta.label}</span>
                  <span style={{ fontSize: '11px', fontFamily: 'monospace', color: meta.color, fontWeight: 700 }}>{pct}%</span>
                </div>
                <div style={{
                  width: '100%', height: '10px', background: '#0B0F19',
                  borderRadius: '5px', overflow: 'hidden'
                }}>
                  <div style={{
                    width: `${pct}%`, height: '100%', background: meta.color,
                    borderRadius: '5px', transition: 'width 0.4s ease',
                    boxShadow: `0 0 8px ${meta.color}55`
                  }} />
                </div>
                <div style={{ fontSize: '10px', color: '#475569', marginTop: '2px' }}>{meta.description}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Reward history line chart */}
      {rewardData.length > 1 && (
        <div style={{ minHeight: '110px' }}>
          <div style={{ fontSize: '11px', color: '#94A3B8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Activity size={12} /> REWARD HISTORY (last {rewardData.length} steps)
          </div>
          <ResponsiveContainer width="100%" height={100}>
            <LineChart data={rewardData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1C2230" vertical={false} />
              <XAxis dataKey="i" hide />
              <YAxis tick={{ fontSize: 9, fill: '#64748B' }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#0B0F19', border: '1px solid #2A3143', fontSize: '11px' }}
                formatter={(v) => [v.toFixed(2), 'Reward']}
                labelFormatter={() => ''}
              />
              <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="reward" stroke="#10B981" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

    </div>
  );
}

export default RlPanel;
