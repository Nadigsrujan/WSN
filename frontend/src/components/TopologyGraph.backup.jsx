import { useRef, useEffect, useState, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { ZoomIn, ZoomOut, Maximize } from 'lucide-react';

// ── Color constants matching the reference diagram ────────────────────────────
const COLOR_SINK_FILL = '#FFD700';
const COLOR_SINK_STROKE = '#FFF8DC';
const COLOR_CH_FILL = '#7C3AED';
const COLOR_CH_STROKE = '#A78BFA';
const COLOR_CH_DEAD = '#4B5563';
const COLOR_NODE_FILL = '#1D4ED8';
const COLOR_NODE_STROKE = '#60A5FA';
const COLOR_NODE_DEAD = '#374151';

const COLOR_SINK_CH_LINK = '#22C55E';   // Green dashed  (CH → SINK)
const COLOR_CH_MESH_LINK = '#3B82F6';   // Blue solid    (CH ↔ CH backbone)
const COLOR_MEMBER_LINK = '#F97316';   // Orange        (CH → member)
const COLOR_BACKUP_LINK = '#EAB308';   // Yellow dashed (inter-cluster backup)
const COLOR_ACTIVE_PATH = '#FFFFFF';
const COLOR_ALT_PATH = '#A78BFA';

const CLUSTER_OVAL_FILLS = [
  'rgba(59,130,246,0.07)',
  'rgba(34,197,94,0.07)',
  'rgba(249,115,22,0.07)',
  'rgba(168,85,247,0.07)',
  'rgba(6,182,212,0.07)',
];
const CLUSTER_OVAL_STROKES = [
  'rgba(59,130,246,0.45)',
  'rgba(34,197,94,0.45)',
  'rgba(249,115,22,0.45)',
  'rgba(168,85,247,0.45)',
  'rgba(6,182,212,0.45)',
];

// ── Drawing primitives ────────────────────────────────────────────────────────

function drawStar(ctx, cx, cy, r, fill, stroke, lw) {
  const spikes = 5, inner = r * 0.42;
  let rot = (Math.PI / 2) * 3, step = Math.PI / spikes;
  ctx.beginPath();
  ctx.moveTo(cx, cy - r);
  for (let i = 0; i < spikes; i++) {
    ctx.lineTo(cx + Math.cos(rot) * r, cy + Math.sin(rot) * r); rot += step;
    ctx.lineTo(cx + Math.cos(rot) * inner, cy + Math.sin(rot) * inner); rot += step;
  }
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = lw;
  ctx.strokeStyle = stroke;
  ctx.stroke();
}

function drawHexagon(ctx, cx, cy, r, fill, stroke, lw) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i - Math.PI / 6;
    i === 0
      ? ctx.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a))
      : ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
  }
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = lw;
  ctx.strokeStyle = stroke;
  ctx.stroke();
}

function drawCircle(ctx, cx, cy, r, fill, stroke, lw) {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.fillStyle = fill;
  ctx.fill();
  if (lw > 0) { ctx.lineWidth = lw; ctx.strokeStyle = stroke; ctx.stroke(); }
}

// ── Fixed hierarchical layout ─────────────────────────────────────────────────

function computeLayout(nodes, W, H) {
  const pos = {};
  const sinkNode = nodes.find(n => n.id === 'SINK' || n.node_type === 'sink');
  const chNodes = nodes.filter(n => n.is_ch === true);
  const normalNodes = nodes.filter(n => n.id !== 'SINK' && n.node_type !== 'sink' && !n.is_ch);

  const PAD = 72;
  const usableW = W - PAD * 2;

  // SINK at top-center
  if (sinkNode) pos[sinkNode.id] = { fx: W / 2, fy: 68 };

  // CHs in an evenly-spaced horizontal row (~35% down)
  const chY = H * 0.37;
  chNodes.forEach((ch, i) => {
    const x = chNodes.length === 1
      ? W / 2
      : PAD + (i / (chNodes.length - 1)) * usableW;
    pos[ch.id] = { fx: x, fy: chY };
  });

  // Normal nodes grouped below their CH in up to 2 rows
  const clusterMap = {};
  normalNodes.forEach(n => {
    const cid = n.cluster_id ?? 0;
    (clusterMap[cid] = clusterMap[cid] || []).push(n);
  });

  const chXByCluster = {};
  chNodes.forEach(ch => { chXByCluster[ch.cluster_id ?? 0] = pos[ch.id]?.fx ?? W / 2; });

  const memberYBase = H * 0.66;
  const ROW_GAP = 56;
  const SPREAD = 62;

  Object.entries(clusterMap).forEach(([cid, members]) => {
    const chX = chXByCluster[parseInt(cid)] ?? W / 2;
    const n = members.length;
    const perRow = Math.ceil(n / 2);
    members.forEach((node, idx) => {
      const row = Math.floor(idx / perRow);
      const col = idx % perRow;
      const rowCount = row === 0 ? Math.min(perRow, n) : n - perRow;
      const offsetX = rowCount <= 1 ? 0 : ((col / (rowCount - 1)) - 0.5) * SPREAD * 2;
      pos[node.id] = { fx: chX + offsetX, fy: memberYBase + row * ROW_GAP };
    });
  });

  return pos;
}

// ── Cluster boundary ovals (pre-render layer) ─────────────────────────────────

function paintClusterOvals(ctx, nodes, fixedPos) {
  const clusterMap = {};
  nodes.forEach(n => {
    if (n.id === 'SINK' || n.node_type === 'sink') return;
    const cid = n.cluster_id ?? 0;
    (clusterMap[cid] = clusterMap[cid] || []).push(fixedPos[n.id]);
  });

  Object.entries(clusterMap).forEach(([cid, pts]) => {
    const valid = pts.filter(Boolean);
    if (!valid.length) return;
    const xs = valid.map(p => p.fx), ys = valid.map(p => p.fy);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const rx = Math.max((Math.max(...xs) - Math.min(...xs)) / 2 + 42, 58);
    const ry = Math.max((Math.max(...ys) - Math.min(...ys)) / 2 + 50, 58);
    const ci = parseInt(cid) % CLUSTER_OVAL_FILLS.length;

    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI);
    ctx.fillStyle = CLUSTER_OVAL_FILLS[ci];
    ctx.fill();
    ctx.setLineDash([8, 5]);
    ctx.strokeStyle = CLUSTER_OVAL_STROKES[ci];
    ctx.lineWidth = 1.8;
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

// ── Edge classifier ───────────────────────────────────────────────────────────

function classifyEdge(link, allNodes, pathSet, altPathSet) {
  const sId = link.source?.id ?? link.source;
  const tId = link.target?.id ?? link.target;
  const key = `${sId}-${tId}`, keyR = `${tId}-${sId}`;

  if (pathSet.has(key) || pathSet.has(keyR)) return 'active';
  if (altPathSet.has(key) || altPathSet.has(keyR)) return 'alt';

  if (link.link_type === 'backup' || link.type === 'backup') return 'backup';

  const nm = {};
  allNodes.forEach(n => { nm[n.id] = n; });
  const sn = nm[sId], tn = nm[tId];

  if (sId === 'SINK' || tn?.node_type === 'sink' || tId === 'SINK' || sn?.node_type === 'sink')
    return 'sink_ch';
  if (sn?.is_ch && tn?.is_ch) return 'ch_mesh';
  return 'member';
}

// ── Main Component ────────────────────────────────────────────────────────────

function TopologyGraph({ graphData, currentPath, altPath }) {
  const fgRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 700, height: 460 });
  const [hasInitialZoomed, setHasInitialZoomed] = useState(false);

  // Handle Zooming functions
  const handleZoomIn = useCallback(() => {
    const currentZoom = fgRef.current.zoom();
    fgRef.current.zoom(currentZoom * 1.5, 400);
  }, []);

  const handleZoomOut = useCallback(() => {
    const currentZoom = fgRef.current.zoom();
    fgRef.current.zoom(currentZoom / 1.5, 400);
  }, []);

  const handleResetZoom = useCallback(() => {
    fgRef.current.zoomToFit(400, 40);
  }, []);

  useEffect(() => {
    const el = document.getElementById('graph-container');
    if (!el) return;
    const update = () =>
      setDimensions({ width: el.clientWidth || 700, height: el.clientHeight || 460 });
    const obs = new ResizeObserver(update);
    obs.observe(el);
    update();
    return () => obs.disconnect();
  }, []);

  if (!graphData?.nodes?.length) {
    return (
      <div style={{ padding: 24, color: '#64748B', textAlign: 'center' }}>
        Waiting for topology data…
      </div>
    );
  }

  // Build path sets
  const pathSet = new Set(), altPathSet = new Set();
  (currentPath ?? []).forEach((id, i, arr) => {
    if (i < arr.length - 1) {
      pathSet.add(`${id}-${arr[i + 1]}`);
      pathSet.add(`${arr[i + 1]}-${id}`);
    }
  });
  (altPath ?? []).forEach((id, i, arr) => {
    if (i < arr.length - 1) {
      altPathSet.add(`${id}-${arr[i + 1]}`);
      altPathSet.add(`${arr[i + 1]}-${id}`);
    }
  });

  const { width: W, height: H } = dimensions;
  const fixedPos = computeLayout(graphData.nodes, W, H);

  const fgData = {
    nodes: graphData.nodes.map(n => ({
      ...n,
      fx: fixedPos[n.id]?.fx ?? W / 2,
      fy: fixedPos[n.id]?.fy ?? H / 2,
      vx: 0, vy: 0,
    })),
    links: (graphData.edges ?? []).map(e => ({ ...e })),
  };

  return (
    <div
      id="graph-container"
      style={{ 
        width: '100%', 
        height: '100%', 
        minHeight: 420, 
        background: '#05090F',
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      {/* Zoom Controls Overlay */}
      <div style={{
        position: 'absolute',
        top: '16px',
        right: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        zIndex: 10,
      }}>
        <button 
          onClick={handleZoomIn}
          className="graph-control-btn"
          title="Zoom In"
        >
          <ZoomIn size={20} />
        </button>
        <button 
          onClick={handleZoomOut}
          className="graph-control-btn"
          title="Zoom Out"
        >
          <ZoomOut size={20} />
        </button>
        <button 
          onClick={handleResetZoom}
          className="graph-control-btn"
          title="Fit to Screen"
        >
          <Maximize size={20} />
        </button>
      </div>
      <ForceGraph2D
        ref={fgRef}
        width={W}
        height={H}
        graphData={fgData}
        nodeId="id"
        d3AlphaDecay={1}
        d3VelocityDecay={1}
        cooldownTicks={0}
        warmupTicks={0}
        enableNodeDrag={true}
        onEngineStop={() => {
          if (!hasInitialZoomed) {
            fgRef.current?.zoomToFit(400, 40);
            setHasInitialZoomed(true);
          }
        }}

        // ── Background: cluster ovals ──────────────────────────────────────
        onRenderFramePre={(ctx) => {
          paintClusterOvals(ctx, graphData.nodes, fixedPos);
        }}

        // ── Node rendering ─────────────────────────────────────────────────
        nodeCanvasObject={(node, ctx, gs) => {
          const { id, alive = true, energy = 100, node_type, is_ch } = node;
          const isSink = id === 'SINK' || node_type === 'sink';
          const isCH = is_ch === true;
          const isAlive = alive !== false;
          const isOnPath = currentPath?.includes(id);
          const isOnAltPath = altPath?.includes(id);
          const x = node.x, y = node.y;

          if (isSink) {
            // Outer glow halo
            const grad = ctx.createRadialGradient(x, y, 6, x, y, 36);
            grad.addColorStop(0, 'rgba(255,215,0,0.28)');
            grad.addColorStop(1, 'rgba(255,215,0,0)');
            ctx.beginPath();
            ctx.arc(x, y, 36, 0, 2 * Math.PI);
            ctx.fillStyle = grad;
            ctx.fill();

            // Star shape
            drawStar(ctx, x, y, 18,
              isAlive ? COLOR_SINK_FILL : '#555',
              isAlive ? COLOR_SINK_STROKE : '#666',
              2 / gs
            );

            // "SINK" label above the star
            ctx.font = `bold ${14 / gs}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillStyle = COLOR_SINK_FILL;
            ctx.fillText('SINK', x, y - 22);

          } else if (isCH) {
            const r = 15;

            // Active path glow
            if (isOnPath && isAlive) {
              ctx.beginPath();
              ctx.arc(x, y, r + 8, 0, 2 * Math.PI);
              ctx.fillStyle = 'rgba(255,255,255,0.10)';
              ctx.fill();
            }

            // Outer subtle ring
            if (isAlive) {
              ctx.beginPath();
              ctx.arc(x, y, r + 6, 0, 2 * Math.PI);
              ctx.strokeStyle = 'rgba(167,139,250,0.22)';
              ctx.lineWidth = 1.5 / gs;
              ctx.stroke();
            }

            const fill = isAlive ? COLOR_CH_FILL : COLOR_CH_DEAD;
            const stroke = isAlive ? COLOR_CH_STROKE : '#555';
            drawHexagon(ctx, x, y, r, fill, stroke, 2 / gs);

            // Label inside hexagon
            ctx.font = `bold ${9 / gs}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = isAlive ? '#FFFFFF' : '#6B7280';
            ctx.fillText(id, x, y);

            // Dead X
            if (!isAlive) {
              const s = 9;
              ctx.beginPath();
              ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s);
              ctx.moveTo(x + s, y - s); ctx.lineTo(x - s, y + s);
              ctx.strokeStyle = '#EF4444';
              ctx.lineWidth = 1.8 / gs;
              ctx.stroke();
            }

          } else {
            // Normal node
            const r = isAlive ? Math.max(6, (energy / 100) * 9) : 5;
            const fill = isAlive ? COLOR_NODE_FILL : COLOR_NODE_DEAD;
            const stroke = isAlive ? COLOR_NODE_STROKE : '#555';

            // Path glow
            if (isOnPath && isAlive) {
              ctx.beginPath();
              ctx.arc(x, y, r + 5, 0, 2 * Math.PI);
              ctx.fillStyle = 'rgba(255,255,255,0.10)';
              ctx.fill();
            }

            // Alt-path ring
            if (isOnAltPath && !isOnPath) {
              ctx.setLineDash([3 / gs, 3 / gs]);
              ctx.beginPath();
              ctx.arc(x, y, r + 5, 0, 2 * Math.PI);
              ctx.strokeStyle = COLOR_ALT_PATH;
              ctx.lineWidth = 1 / gs;
              ctx.stroke();
              ctx.setLineDash([]);
            }

            drawCircle(ctx, x, y, r, fill, stroke, 1.5 / gs);

            // Label inside circle
            ctx.font = `bold ${8 / gs}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = isAlive ? '#FFFFFF' : '#6B7280';
            ctx.fillText(id, x, y);

            // Dead X
            if (!isAlive) {
              const s = 5;
              ctx.beginPath();
              ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s);
              ctx.moveTo(x + s, y - s); ctx.lineTo(x - s, y + s);
              ctx.strokeStyle = '#EF4444';
              ctx.lineWidth = 1.4 / gs;
              ctx.stroke();
            }
          }
        }}

        nodePointerAreaPaint={(node, color, ctx) => {
          const r = node.id === 'SINK' ? 20 : node.is_ch ? 17 : 10;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}

        // ── Edge rendering ─────────────────────────────────────────────────
        linkCanvasObject={(link, ctx, gs) => {
          const sx = link.source?.x ?? 0, sy = link.source?.y ?? 0;
          const tx = link.target?.x ?? 0, ty = link.target?.y ?? 0;
          const type = classifyEdge(link, graphData.nodes, pathSet, altPathSet);

          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(tx, ty);
          ctx.setLineDash([]);

          switch (type) {
            case 'active':
              ctx.strokeStyle = COLOR_ACTIVE_PATH;
              ctx.lineWidth = 3.5 / gs;
              break;
            case 'alt':
              ctx.strokeStyle = COLOR_ALT_PATH;
              ctx.lineWidth = 2 / gs;
              ctx.setLineDash([6 / gs, 4 / gs]);
              break;
            case 'sink_ch':
              ctx.strokeStyle = COLOR_SINK_CH_LINK;
              ctx.lineWidth = 1.6 / gs;
              ctx.setLineDash([7 / gs, 5 / gs]);
              break;
            case 'ch_mesh':
              ctx.strokeStyle = COLOR_CH_MESH_LINK;
              ctx.lineWidth = 2.2 / gs;
              break;
            case 'backup':
              ctx.strokeStyle = COLOR_BACKUP_LINK;
              ctx.lineWidth = 1.6 / gs;
              ctx.setLineDash([8 / gs, 5 / gs]);
              break;
            default: // member
              ctx.strokeStyle = COLOR_MEMBER_LINK;
              ctx.lineWidth = 1.4 / gs;
              break;
          }

          ctx.stroke();
          ctx.setLineDash([]);
        }}
        linkCanvasObjectMode={() => 'replace'}

        // Animated particles on active path
        linkDirectionalParticles={link => {
          const sId = link.source?.id ?? link.source;
          const tId = link.target?.id ?? link.target;
          return pathSet.has(`${sId}-${tId}`) ? 4 : 0;
        }}
        linkDirectionalParticleSpeed={0.007}
        linkDirectionalParticleWidth={3}
        linkDirectionalParticleColor={() => '#FFFFFF'}
      />
    </div>
  );
}

export default TopologyGraph;
