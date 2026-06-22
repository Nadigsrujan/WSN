import React, { useMemo, useState, useEffect, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize } from 'lucide-react';

// ── Constants ─────────────────────────────────────────────────────────────────
const SVG_W = 1600;
const SVG_H = 900;
const PAD_X = 130;
const PAD_Y = 90;

const toSVG = (x, y) => ({
  sx: PAD_X + (x / 100) * (SVG_W - 2 * PAD_X),
  sy: SVG_H - PAD_Y - (y / 100) * (SVG_H - 2 * PAD_Y),
});

// ── Color helpers ─────────────────────────────────────────────────────────────
const energyColor = (e, alive) => {
  if (!alive) return '#475569';
  if (e > 66)  return '#10B981';
  if (e > 33)  return '#F59E0B';
  return '#EF4444';
};

const CLUSTER_CLR = {
  stroke: ['#3b82f6', '#22c55e', '#f97316'],
  fill:   ['#3b82f608', '#22c55e08', '#f9731608'],
  label:  ['#5b8dee', '#4ade80', '#fb923c'],
};

// Edge colors — these are the PERMANENT visual colors, never dimmed
const EDGE_CLR = {
  intra:  '#06b6d4',   // Teal — intra-cluster mesh
  inter:  '#3b82f6',   // Blue — CH-to-CH backbone
  sink:   '#22c55e',   // Green — CH-to-SINK
  active: '#ffffff',   // White — packet flow overlay
};

const CH_COLOR = '#f59e0b'; // Gold for cluster heads

// ── Packet dot animated along a path ─────────────────────────────────────────
function PacketDot({ pathD, dur = '2s', delay = '0s' }) {
  return (
    <circle r={7} fill="#ffffff" opacity={0.95} filter="url(#glow-strong)">
      <animateMotion dur={dur} begin={delay} repeatCount="indefinite" path={pathD} />
    </circle>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function TopologyGraph({ graphData, currentPath, altPath, chEvents }) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan]   = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState(null);

  const onWheel = useCallback(e => {
    e.preventDefault();
    setZoom(z => Math.min(4, Math.max(0.2, z * (e.deltaY > 0 ? 0.9 : 1.1))));
  }, []);
  const onMD = e => { if (e.button === 0) setDrag({ sx: e.clientX - pan.x, sy: e.clientY - pan.y }); };
  const onMM = useCallback(e => { if (drag) setPan({ x: e.clientX - drag.sx, y: e.clientY - drag.sy }); }, [drag]);
  const onMU = () => setDrag(null);

  useEffect(() => {
    window.addEventListener('mousemove', onMM);
    window.addEventListener('mouseup', onMU);
    return () => { window.removeEventListener('mousemove', onMM); window.removeEventListener('mouseup', onMU); };
  }, [onMM]);

  // ── Build topology from graph data ─────────────────────────────────────────
  const topo = useMemo(() => {
    if (!graphData?.nodes?.length) {
      return { nodeMap: {}, edges: [], clusters: {}, sinkPos: toSVG(50, 90) };
    }

    // Build nodeMap
    const nodeMap = {};
    graphData.nodes.forEach(n => {
      const id = n.node_id || n.id;
      if (!id) return;
      const { sx, sy } = toSVG(n.x ?? 50, n.y ?? 50);
      nodeMap[id] = {
        ...n, id, sx, sy,
        alive:      n.alive !== false,
        is_ch:      n.is_ch || false,
        cluster_id: n.cluster_id ?? -1,
        energy:     n.energy ?? 0,
        node_type:  n.node_type || 'virtual',
      };
    });

    // Group by cluster — ALIVE nodes only (dead nodes don't count toward
    // cluster boundary or membership display)
    const clusters = {};
    Object.values(nodeMap).forEach(n => {
      if (n.id === 'SINK' || n.cluster_id < 0 || !n.alive) return;
      (clusters[n.cluster_id] = clusters[n.cluster_id] || []).push(n);
    });

    // Build DEDUPLICATED edge list
    // The backend may send both (A,B) and (B,A) — we collapse to one line per pair.
    const seen = new Set();
    const edges = [];

    if (graphData.edges) {
      graphData.edges.forEach(e => {
        const src = nodeMap[e.source];
        const tgt = nodeMap[e.target];
        if (!src || !tgt || !src.alive || !tgt.alive) return;

        // Canonical dedup key — always sort IDs so A-B == B-A
        const key = [e.source, e.target].sort().join('|');
        if (seen.has(key)) return;
        seen.add(key);

        // Classify edge type
        const isSink = e.source === 'SINK' || e.target === 'SINK';
        const sameCluster = src.cluster_id === tgt.cluster_id && src.cluster_id >= 0;

        let edgeType;
        if (isSink) {
          edgeType = 'sink';
        } else if (!sameCluster) {
          edgeType = 'inter'; // CH-to-CH backbone
        } else {
          edgeType = 'intra'; // intra-cluster mesh
        }

        edges.push({ src, tgt, edgeType, key });
      });
    }

    return {
      nodeMap,
      edges,
      clusters,
      sinkPos: nodeMap['SINK'] || { sx: toSVG(50, 90).sx, sy: toSVG(50, 90).sy },
    };
  }, [graphData]);

  // ── Active path set ────────────────────────────────────────────────────────
  // Build a set of canonical edge keys AND a direction map so the animated
  // overlay always flows in the correct CH→SINK direction, regardless of
  // which order the backend stored the edge (some sink edges arrive as SINK→CH).
  const { activeEdgeKeys, pathDirectionMap } = useMemo(() => {
    const keys = new Set();
    const dirMap = {};
    if (!currentPath || currentPath.length < 2) return { activeEdgeKeys: keys, pathDirectionMap: dirMap };
    for (let k = 0; k < currentPath.length - 1; k++) {
      const a = currentPath[k];
      const b = currentPath[k + 1];
      const key = [a, b].sort().join('|');
      keys.add(key);
      dirMap[key] = { from: a, to: b }; // canonical direction from the actual path
    }
    return { activeEdgeKeys: keys, pathDirectionMap: dirMap };
  }, [currentPath]);

  // ── Build SVG path string for the active route (for packet animation) ──────
  const primaryPathD = useMemo(() => {
    if (!currentPath || currentPath.length < 2) return null;
    const pts = currentPath.map(id => topo.nodeMap[id]).filter(Boolean);
    if (pts.length < 2) return null;
    return 'M ' + pts.map(n => `${n.sx},${n.sy}`).join(' L ');
  }, [topo, currentPath]);

  // ── Cluster ellipses ───────────────────────────────────────────────────────
  const clusterBounds = useMemo(() => {
    return Object.entries(topo.clusters).map(([cid, members]) => {
      const cidNum = parseInt(cid);
      if (!members.length) return null;
      const allSX = members.map(m => m.sx);
      const allSY = members.map(m => m.sy);
      const minX = Math.min(...allSX), maxX = Math.max(...allSX);
      const minY = Math.min(...allSY), maxY = Math.max(...allSY);
      return {
        cid: cidNum,
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
        rx: Math.max(65, (maxX - minX) / 2 + 58),
        ry: Math.max(65, (maxY - minY) / 2 + 58),
        stroke: CLUSTER_CLR.stroke[cidNum % 3],
        fill:   CLUSTER_CLR.fill[cidNum % 3],
        label:  CLUSTER_CLR.label[cidNum % 3],
      };
    }).filter(Boolean);
  }, [topo.clusters]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#050a14', overflow: 'hidden', userSelect: 'none', borderRadius: 12 }}>
      <style>{`
        /*
          dashflow animates stroke-dashoffset on the OVERLAY line.
          The base line (drawn separately) is always solid — so links
          are NEVER invisible regardless of animation state.
        */
        @keyframes dashflow {
          from { stroke-dashoffset: 44; }
          to   { stroke-dashoffset: 0; }
        }
        @keyframes pulse-ch {
          0%, 100% { stroke-opacity: 0.2; }
          50%       { stroke-opacity: 0.8; }
        }
      `}</style>

      {/* Zoom controls */}
      <div style={{ position: 'absolute', bottom: 20, right: 20, zIndex: 20, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button onClick={() => setZoom(z => Math.min(4, z * 1.2))} style={{ background: '#1e293b', color: '#fff', border: '1px solid #334155', padding: 8, borderRadius: 6, cursor: 'pointer' }}><ZoomIn size={18} /></button>
        <button onClick={() => setZoom(z => Math.max(0.2, z / 1.2))} style={{ background: '#1e293b', color: '#fff', border: '1px solid #334155', padding: 8, borderRadius: 6, cursor: 'pointer' }}><ZoomOut size={18} /></button>
        <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} style={{ background: '#1e293b', color: '#fff', border: '1px solid #334155', padding: 8, borderRadius: 6, cursor: 'pointer' }}><Maximize size={18} /></button>
      </div>

      <div onMouseDown={onMD} onWheel={onWheel} style={{ width: '100%', height: '100%', cursor: drag ? 'grabbing' : 'grab' }}>
        <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} style={{ width: '100%', height: '100%' }} preserveAspectRatio="xMidYMid meet">
          <defs>
            <filter id="glow-xl"     x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="12" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <filter id="glow-strong" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"  result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <filter id="glow-soft"   x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="3"  result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <filter id="glow-amber"  x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5"  result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          </defs>

          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>

            {/* ══ LAYER 1: Cluster boundary ellipses ══════════════════════════ */}
            {clusterBounds.map(b => (
              <g key={`bnd-${b.cid}`}>
                <ellipse cx={b.cx} cy={b.cy} rx={b.rx} ry={b.ry} fill={b.fill} />
                <ellipse cx={b.cx} cy={b.cy} rx={b.rx} ry={b.ry} fill="none"
                  stroke={b.stroke} strokeWidth={1.5} strokeDasharray="10 6" opacity={0.5} />
                <text x={b.cx} y={b.cy + b.ry + 24} textAnchor="middle"
                  fontSize={15} fill={b.label} fontWeight="800" fontFamily="'JetBrains Mono',monospace">
                  Cluster {b.cid + 1}
                </text>
              </g>
            ))}

            {/*
              ══ LAYER 2A: PERMANENT BASE LINES ══════════════════════════════
              Every edge is drawn as a solid permanent line.
              These lines are NEVER removed or made invisible.
              Active edges keep their full color — the white overlay is drawn
              on top in layer 2B, never replacing this line.
            */}
            {topo.edges.map((e, i) => {
              const isActive = activeEdgeKeys.has(e.key);
              const color = e.edgeType === 'sink'  ? EDGE_CLR.sink
                          : e.edgeType === 'inter' ? EDGE_CLR.inter
                          : EDGE_CLR.intra;
              const width   = e.edgeType === 'intra' ? 1.8 : 2.5;
              const dash    = e.edgeType === 'sink'  ? '12 7' : undefined;
              // opacity is ALWAYS the same whether active or not
              const opacity = e.edgeType === 'intra' ? 0.55 : 0.75;

              return (
                <line key={`base-${i}`}
                  x1={e.src.sx} y1={e.src.sy}
                  x2={e.tgt.sx} y2={e.tgt.sy}
                  stroke={color}
                  strokeWidth={width}
                  strokeDasharray={dash}
                  opacity={opacity}
                />
              );
            })}

            {/*
              ══ LAYER 2B: ANIMATED FLOW OVERLAY (active path only) ══════════
              Only drawn for edges on the current route.
              Direction is taken from pathDirectionMap so the dashes always
              flow CH → SINK (not SINK → CH), regardless of how the backend
              stored the edge internally.
            */}
            {topo.edges.map((e, i) => {
              if (!activeEdgeKeys.has(e.key)) return null;
              // Use path-ordered direction so animation always flows source→sink
              const dir = pathDirectionMap[e.key];
              const fromNode = dir ? topo.nodeMap[dir.from] : e.src;
              const toNode   = dir ? topo.nodeMap[dir.to]   : e.tgt;
              if (!fromNode || !toNode) return null;
              return (
                <line key={`flow-${i}`}
                  x1={fromNode.sx} y1={fromNode.sy}
                  x2={toNode.sx}   y2={toNode.sy}
                  stroke="#ffffff"
                  strokeWidth={4.5}
                  strokeDasharray="14 8"
                  strokeLinecap="round"
                  opacity={0.85}
                  filter="url(#glow-soft)"
                  style={{ animation: 'dashflow 0.65s linear infinite' }}
                />
              );
            })}

            {/* ══ LAYER 3: ONE packet dot moving along active path ══════════
              Using a single dot eliminates the visual ambiguity of two dots
              appearing to travel in opposite directions on the same link.
            */}
            {primaryPathD && (
              <PacketDot pathD={primaryPathD} dur="2s" />
            )}

            {/* ══ LAYER 4: SINK diamond ════════════════════════════════════════ */}
            {topo.sinkPos && (() => {
              const s = topo.sinkPos;
              const sx = s.sx ?? s.x;
              const sy = s.sy ?? s.y;
              return (
                <g filter="url(#glow-xl)">
                  <rect x={sx - 52} y={sy - 52} width={104} height={104}
                    fill="#EF4444" stroke="#fecaca" strokeWidth={3}
                    transform={`rotate(45,${sx},${sy})`} />
                  <text x={sx} y={sy - 74} textAnchor="middle" fontSize={22}
                    fontWeight="900" fill="#EF4444" fontFamily="'JetBrains Mono',monospace"
                    filter="url(#glow-soft)">
                    SINK
                  </text>
                </g>
              );
            })()}

            {/* ══ LAYER 5: Sensor / relay nodes ════════════════════════════
              Dead nodes are completely hidden — removed from the display.
              Only alive nodes are rendered.
            ══════════════════════════════════════════════════════════════ */}
            {Object.values(topo.nodeMap).map(n => {
              if (n.id === 'SINK') return null;
              if (!n.alive) return null;
              const isCH   = n.is_ch;
              const isReal = n.node_type === 'real' || n.node_type === 'wokwi';
              const eCol   = energyColor(n.energy, n.alive);
              const R = 32;

              const stroke = isCH ? CH_COLOR : isReal ? '#F59E0B' : eCol;
              const fill   = isCH ? '#1a1000' : isReal ? '#1c1107' : '#0c1830';
              const sw     = isCH ? 4.5 : isReal ? 3.5 : 2.5;

              return (
                <g key={n.id}>
                  {/* Ambient halo */}
                  <circle cx={n.sx} cy={n.sy} r={R + 26}
                    fill={`${isCH ? CH_COLOR : eCol}0b`} />

                  {/* CH pulsing outer ring */}
                  {isCH && (
                    <circle cx={n.sx} cy={n.sy} r={R + 14}
                      fill="none" stroke={CH_COLOR} strokeWidth={2}
                      style={{ animation: 'pulse-ch 2s ease-in-out infinite' }} />
                  )}

                  {/* Node body */}
                  <circle cx={n.sx} cy={n.sy} r={R}
                    fill={fill} stroke={stroke} strokeWidth={sw}
                    filter="url(#glow-soft)" />

                  {/* CH crown label above node */}
                  {isCH && (
                    <text x={n.sx} y={n.sy - R - 10}
                      textAnchor="middle" fontSize={14}
                      fontWeight="900" fill={CH_COLOR}
                      fontFamily="'JetBrains Mono',monospace"
                      filter="url(#glow-amber)">
                      ★ CH
                    </text>
                  )}

                  {/* Node ID */}
                  <text x={n.sx} y={n.sy - 2}
                    textAnchor="middle" fontSize={11} fontWeight="800"
                    fill="#fff" fontFamily="'JetBrains Mono',monospace">
                    {n.id}
                  </text>

                  {/* HW badge */}
                  {isReal && n.alive && (
                    <text x={n.sx} y={n.sy + 12}
                      textAnchor="middle" fontSize={9} fill="#F59E0B"
                      fontWeight="800" fontFamily="Inter,sans-serif">
                      HW
                    </text>
                  )}

                  {/* Energy */}
                  <text x={n.sx} y={n.sy + (isReal ? 24 : 14)}
                    textAnchor="middle" fontSize={10} fill={eCol}
                    fontFamily="Inter,sans-serif" fontWeight="700">
                    {Math.round(n.energy ?? 0)}%
                  </text>

                </g>
              );
            })}

          </g>
        </svg>
      </div>
    </div>
  );
}
