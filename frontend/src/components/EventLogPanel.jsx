import { useEffect, useRef } from 'react';
import { AlertTriangle, Info, RefreshCw } from 'lucide-react';

function EventLogPanel({ events }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  if (!events || events.length === 0) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: '#475569', fontSize: '13px', gap: '8px'
      }}>
        <Info size={16} /> No events yet…
      </div>
    );
  }

  const getIcon = (type) => {
    switch (type) {
      case 'warning': return <AlertTriangle size={12} color="#F59E0B" />;
      case 'reroute': return <RefreshCw size={12} color="#8B5CF6" />;
      default:        return <Info size={12} color="#3B82F6" />;
    }
  };

  const getColor = (type) => {
    switch (type) {
      case 'warning': return '#F59E0B';
      case 'reroute': return '#8B5CF6';
      default:        return '#94A3B8';
    }
  };

  const getBgColor = (type) => {
    switch (type) {
      case 'warning': return 'rgba(245, 158, 11, 0.05)';
      case 'reroute': return 'rgba(139, 92, 246, 0.05)';
      default:        return 'transparent';
    }
  };

  const formatTime = (ts) => {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false });
  };

  return (
    <div
      ref={scrollRef}
      className="event-log-container"
    >
      {events.map((evt, i) => (
        <div
          key={i}
          className="event-log-item"
          style={{ backgroundColor: getBgColor(evt.type) }}
        >
          <div className="event-log-icon">
            {getIcon(evt.type)}
          </div>
          <div className="event-log-time">
            {formatTime(evt.timestamp)}
          </div>
          <div className="event-log-message" style={{ color: getColor(evt.type) }}>
            {evt.message}
          </div>
        </div>
      ))}
    </div>
  );
}

export default EventLogPanel;
