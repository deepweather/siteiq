import { useEffect, useRef, useState, useCallback } from 'react';
import type { AssetUpdate, Trail } from '../types/assets';
import type { WasteSummary } from '../types/analytics';

interface WebSocketState {
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  trailsRef: React.MutableRefObject<Trail>;
  analytics: WasteSummary | null;
  simTime: number;
  simDay: number;
  connected: boolean;
}

export function useWebSocket(): WebSocketState {
  const assetsRef = useRef<AssetUpdate[]>([]);
  const trailsRef = useRef<Trail>({});
  const [analytics, setAnalytics] = useState<WasteSummary | null>(null);
  const [simTime, setSimTime] = useState(0);
  const [simDay, setSimDay] = useState(47);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const reconnectDelay = useRef(1000);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket('ws://localhost:8000/ws');
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      reconnectDelay.current = 1000;
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'state_update') {
        assetsRef.current = data.assets;
        trailsRef.current = data.trails;
        setSimTime(data.sim_time);
        setSimDay(data.sim_day);
        if (data.analytics) {
          setAnalytics(data.analytics);
        }
      }
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = window.setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, 10000);
        connect();
      }, reconnectDelay.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { assetsRef, trailsRef, analytics, simTime, simDay, connected };
}
