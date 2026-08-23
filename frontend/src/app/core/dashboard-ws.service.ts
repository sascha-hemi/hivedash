import { Injectable, signal } from '@angular/core';

import { DashboardResponse } from './models';

/** Live push counterpart to DashboardService.fetch() - same session cookie (browsers attach
 * cookies to a same-origin WebSocket handshake automatically), same per-user resolved dashboard.
 * The server sends one snapshot right after connecting, then another every time a poll completes
 * (see app.main's DashboardConnectionManager) - this service only ever receives, never sends. */
@Injectable({ providedIn: 'root' })
export class DashboardWsService {
  private socket: WebSocket | null = null;
  private reconnectDelayMs = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private reconnectingIndicatorTimer: ReturnType<typeof setTimeout> | undefined;
  private manuallyClosed = false;

  readonly data = signal<DashboardResponse | null>(null);
  readonly connected = signal(false);
  /** True only once the connection has actually been down for a moment - a normal, near-instant
   * reconnect (the common case) never sets this, so it doesn't flash a message for something the
   * user wouldn't otherwise notice. Only a real outage (e.g. a server restart) surfaces it. */
  readonly reconnecting = signal(false);

  connect(): void {
    this.manuallyClosed = false;
    this.open();
  }

  disconnect(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.reconnectingIndicatorTimer) clearTimeout(this.reconnectingIndicatorTimer);
    this.socket?.close();
    this.socket = null;
  }

  private open(): void {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${location.host}/api/ws/dashboard`);
    this.socket = socket;

    socket.onopen = () => {
      this.connected.set(true);
      this.reconnectDelayMs = 1000;
      if (this.reconnectingIndicatorTimer) clearTimeout(this.reconnectingIndicatorTimer);
      this.reconnecting.set(false);
    };
    socket.onmessage = (event) => {
      try {
        this.data.set(JSON.parse(event.data));
      } catch {
        // malformed frame - ignore, the next push will correct itself
      }
    };
    socket.onclose = () => {
      this.connected.set(false);
      if (this.manuallyClosed || this.socket !== socket) return;
      this.reconnectingIndicatorTimer = setTimeout(() => this.reconnecting.set(true), 1200);
      this.reconnectTimer = setTimeout(() => this.open(), this.reconnectDelayMs);
      this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, 30000);
    };
    socket.onerror = () => socket.close();
  }
}
