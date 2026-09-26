"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Control, Snapshot, StateField } from "./types";

export function apiUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  return typeof window === "undefined" ? "http://localhost:8000" : `${window.location.protocol}//${window.location.hostname}:8000`;
}

export async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${apiUrl()}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch { /* Preserve the HTTP error when a proxy returns non-JSON. */ }
    throw new Error(message);
  }
  return response.json();
}

export function useDashboard() {
  const [state, setState] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<"connecting" | "connected" | "polling" | "offline">("connecting");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const mounted = useRef(true);
  const accept = useCallback((next: Snapshot, newConnection = false) => {
    if (mounted.current) setState((previous) => newConnection || !previous || next.revision >= previous.revision ? next : previous);
  }, []);

  useEffect(() => {
    mounted.current = true;
    let closed = false;
    let socket: WebSocket | undefined;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let fetching = false;

    async function poll() {
      if (closed || fetching) return;
      fetching = true;
      try {
        const next = await request<Snapshot>("/api/state");
        if (!closed) {
          // A restarted API begins a new revision sequence. Polling may be the
          // only working transport, so allow that new sequence while offline.
          accept(next, socket?.readyState !== WebSocket.OPEN);
          setConnection(socket?.readyState === WebSocket.OPEN ? "connected" : "polling");
        }
      } catch {
        if (!closed && socket?.readyState !== WebSocket.OPEN) setConnection("offline");
      } finally { fetching = false; }
    }

    function connect() {
      if (closed) return;
      let firstSnapshot = true;
      socket = new WebSocket(`${apiUrl().replace(/^http/, "ws")}/ws`);
      socket.onopen = () => { attempt = 0; if (!closed) setConnection("connected"); };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === "snapshot" && message.data) {
            accept(message.data, firstSnapshot);
            firstSnapshot = false;
          }
        } catch { /* A malformed message must not break the dashboard. */ }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (closed) return;
        setConnection("polling");
        void poll();
        reconnect = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
      };
    }
    void poll();
    connect();
    const timer = setInterval(() => { if (socket?.readyState !== WebSocket.OPEN) void poll(); }, 4000);
    return () => {
      closed = true;
      mounted.current = false;
      clearInterval(timer);
      clearTimeout(reconnect);
      socket?.close();
    };
  }, [accept]);

  const mutate = useCallback(async (path: string, method: string, body: unknown) => {
    setPending(true);
    setError(null);
    try { accept(await request<Snapshot>(path, method, body)); }
    catch (error) { setError(error instanceof Error ? error.message : "Unable to update the dashboard. Try again."); }
    finally { setPending(false); }
  }, [accept]);

  const control = useCallback((value: Control) => mutate("/api/control", "POST", value), [mutate]);
  const updateWorker = useCallback((id: string, value: Partial<Record<StateField, number>>) => mutate(`/api/workers/${encodeURIComponent(id)}/state`, "PATCH", value), [mutate]);
  return { state, connection, error, pending, control, updateWorker, mutate, clearError: () => setError(null) };
}
