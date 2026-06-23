import { useEffect, useRef, useState, useCallback } from 'react';
import type { AssetUpdate, Trail } from '../types/assets';
import type { WasteSummary } from '../types/analytics';
import { WS_BASE } from '../services/api';

/** Live cab summary streamed at 10 Hz alongside the state update.
 *  Used by the renderer to draw queue counts on stair/elevator anchors. */
export interface CabSnapshot {
  id: string;
  current_level: string;
  passengers: number;
  capacity: number;
  /** Map of level_id → queue depth (only levels with non-empty queues). */
  queue_by_level: Record<string, number>;
}

interface WebSocketState {
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  trailsRef: React.MutableRefObject<Trail>;
  cabsRef: React.MutableRefObject<CabSnapshot[]>;
  analytics: WasteSummary | null;
  simTime: number;
  simDay: number;
  connected: boolean;
}

export function useWebSocket(): WebSocketState {
  const assetsRef = useRef<AssetUpdate[]>([]);
  const trailsRef = useRef<Trail>({});
  const cabsRef = useRef<CabSnapshot[]>([]);
  const [analytics, setAnalytics] = useState<WasteSummary | null>(null);
  const [simTime, setSimTime] = useState(0);
  const [simDay, setSimDay] = useState(47);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const reconnectDelay = useRef(1000);

  const connect = useCallback(() => {
    // Skip if an existing socket is OPEN or still CONNECTING (race during
    // reconnect could otherwise spawn parallel sockets).
    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const ws = new WebSocket(`${WS_BASE}/ws`);
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
        cabsRef.current = data.cabs ?? [];
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

  return { assetsRef, trailsRef, cabsRef, analytics, simTime, simDay, connected };
}
