import { useRef, useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

function TopologyGraph({ graphData, currentPath, altPath, nodesMap }) {
  const fgRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });

  // Handle resizing
  useEffect(() => {
    const handleResize = () => {
      const container = document.getElementById('graph-container');
      if (container) {
        setDimensions({ width: container.clientWidth, height: container.clientHeight });
      }
    };
    
    window.addEventListener('resize', handleResize);
    handleResize(); // Initial call
    
    // Slight delay to ensure parent container has rendered
    setTimeout(handleResize, 100);
    
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (!graphData || !graphData.nodes) return <div style={{padding: '20px', color: '#888'}}>Loading graph...</div>;

  // Build path edge sets
  const pathSet = new Set();
  if (currentPath && currentPath.length > 0) {
    for (let i = 0; i < currentPath.length - 1; i++) {
      pathSet.add(`${currentPath[i]}-${currentPath[i+1]}`);
      pathSet.add(`${currentPath[i+1]}-${currentPath[i]}`);
    }
  }

  const altPathSet = new Set();
  if (altPath && altPath.length > 0) {
    for (let i = 0; i < altPath.length - 1; i++) {
      altPathSet.add(`${altPath[i]}-${altPath[i+1]}`);
      altPathSet.add(`${altPath[i+1]}-${altPath[i]}`);
    }
  }

  // Pre-process nodes for force-graph format
  const fgData = {
    nodes: graphData.nodes.map(n => ({ ...n })), // Clone to avoid mutating original
    links: graphData.edges ? graphData.edges.map(e => ({ ...e })) : []
  };

  // Draw hexagon helper
  const drawHexagon = (ctx, x, y, size) => {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i - Math.PI / 6;
      const hx = x + size * Math.cos(angle);
      const hy = y + size * Math.sin(angle);
      if (i === 0) ctx.moveTo(hx, hy);
      else ctx.lineTo(hx, hy);
    }
    ctx.closePath();
  };

  return (
    <div id="graph-container" style={{ width: '100%', height: '100%', minHeight: '400px', backgroundColor: '#0B0F19' }}>
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={fgData}
        nodeId="id"
        // Configure forces
        d3VelocityDecay={0.1}
        cooldownTicks={100}
        onEngineStop={() => {
          if (fgRef.current) {
            fgRef.current.zoomToFit(400, 50);
          }
        }}
        // Custom Node Rendering
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.id;
          const isAlive = node.alive !== false;
          const energy = node.energy !== undefined ? node.energy : 100;
          const nType = node.node_type || 'virtual';
          const isSink = nType === 'sink' || label === 'SINK';
          const isESP32 = nType === 'real' || label.startsWith('ESP32');
          const isOnPath = currentPath && currentPath.includes(label);
          const isOnAltPath = altPath && altPath.includes(label);

          // Node styling
          const size = isSink ? 14 : isESP32 ? 11 : (isAlive ? Math.max(6, (energy / 100) * 10) : 5);
          
          let color = '#475569'; // dead
          if (isAlive) {
            if (energy > 66) color = '#10B981';
            else if (energy > 33) color = '#F59E0B';
            else color = '#EF4444';
          }
          
          let borderColor = '#2A3143';
          if (isSink) borderColor = '#EF4444';
          else if (isESP32) borderColor = '#F59E0B';
          else if (nType === 'wokwi') borderColor = '#3B82F6';
          
          if (isOnPath && isAlive) {
            borderColor = '#fff';
          }

          // Draw node
          if (!isAlive) {
            // Draw cross for dead nodes
            ctx.beginPath();
            ctx.moveTo(node.x - size, node.y - size);
            ctx.lineTo(node.x + size, node.y + size);
            ctx.moveTo(node.x + size, node.y - size);
            ctx.lineTo(node.x - size, node.y + size);
            ctx.strokeStyle = color;
            ctx.lineWidth = 2 / globalScale;
            ctx.stroke();
          } else if (isESP32) {
            // Draw HEXAGON for ESP32 nodes
            drawHexagon(ctx, node.x, node.y, size);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.lineWidth = isOnPath ? 2.5 / globalScale : 1.5 / globalScale;
            ctx.strokeStyle = borderColor;
            ctx.stroke();

            // Glow effect for ESP32
            if (isOnPath) {
              drawHexagon(ctx, node.x, node.y, size + 4);
              ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
              ctx.fill();
            }
          } else if (isSink) {
            // Draw diamond for SINK
            ctx.beginPath();
            ctx.moveTo(node.x, node.y - size);
            ctx.lineTo(node.x + size, node.y);
            ctx.lineTo(node.x, node.y + size);
            ctx.lineTo(node.x - size, node.y);
            ctx.closePath();
            ctx.fillStyle = '#EF4444';
            ctx.fill();
            ctx.lineWidth = 2 / globalScale;
            ctx.strokeStyle = '#fff';
            ctx.stroke();
          } else {
            // Draw circle for regular virtual nodes
            ctx.beginPath();
            ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false);
            ctx.fillStyle = color;
            ctx.fill();
            
            ctx.lineWidth = isOnPath ? 2 / globalScale : 1 / globalScale;
            ctx.strokeStyle = borderColor;
            ctx.stroke();
            
            // Draw pulse if on active path
            if (isOnPath) {
              ctx.beginPath();
              ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI, false);
              ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
              ctx.fill();
            }

            // Draw dashed ring if on alternate path only
            if (isOnAltPath && !isOnPath) {
              ctx.beginPath();
              ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI, false);
              ctx.setLineDash([3 / globalScale, 3 / globalScale]);
              ctx.strokeStyle = 'rgba(139, 92, 246, 0.4)';
              ctx.lineWidth = 1 / globalScale;
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }

          // Draw label
          const fontSize = 12 / globalScale;
          ctx.font = `${isESP32 ? 'bold ' : ''}${fontSize}px Inter, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = isAlive ? '#E2E8F0' : '#64748B';
          ctx.fillText(label, node.x, node.y + size + fontSize);
        }}
        // Edge styling
        linkColor={(edge) => {
          const key = `${edge.source.id || edge.source}-${edge.target.id || edge.target}`;
          if (pathSet.has(key)) return '#3B82F6';
          if (altPathSet.has(key)) return 'rgba(139, 92, 246, 0.5)';
          return edge.lqi > 0.6 ? 'rgba(16, 185, 129, 0.25)' : edge.lqi > 0.3 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(239, 68, 68, 0.15)';
        }}
        linkWidth={(edge) => {
          const key = `${edge.source.id || edge.source}-${edge.target.id || edge.target}`;
          if (pathSet.has(key)) return 3;
          if (altPathSet.has(key)) return 1.5;
          return 0.8;
        }}
        linkLineDash={(edge) => {
          const key = `${edge.source.id || edge.source}-${edge.target.id || edge.target}`;
          if (altPathSet.has(key) && !pathSet.has(key)) return [5, 5];
          return null;
        }}
        linkDirectionalParticles={edge => {
          const key = `${edge.source.id || edge.source}-${edge.target.id || edge.target}`;
          return pathSet.has(key) ? 4 : 0;
        }}
        linkDirectionalParticleSpeed={0.01}
        linkDirectionalParticleWidth={4}
        linkDirectionalParticleColor={() => '#60A5FA'}
      />
    </div>
  );
}

export default TopologyGraph;
