import { Injectable, inject, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface RealtimeMessage {
  type?: string;
  room?: string;
  data?: any;
  [key: string]: any;
}

interface RoomConnection {
  subject: Subject<RealtimeMessage>;
  socket: WebSocket | null;
  reconnectAttempts: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  manualClose: boolean;
  subscriberCount: number;
}

@Injectable({
  providedIn: 'root'
})
export class RealtimeService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly connections = new Map<string, RoomConnection>();
  private readonly maxReconnectDelayMs = 30000;

  connect(room: string): Observable<RealtimeMessage> {
    return new Observable<RealtimeMessage>(observer => {
      if (!this.isBrowser()) {
        observer.complete();
        return;
      }

      const state = this.ensureRoomState(room);
      state.subscriberCount += 1;

      this.openSocket(room);

      const subscription = state.subject.subscribe(observer);

      return () => {
        subscription.unsubscribe();
        const currentState = this.connections.get(room);
        if (!currentState) {
          return;
        }

        currentState.subscriberCount = Math.max(0, currentState.subscriberCount - 1);
        if (currentState.subscriberCount === 0) {
          this.disconnect(room);
        }
      };
    });
  }

  disconnect(room: string): void {
    const state = this.connections.get(room);
    if (!state) {
      return;
    }

    state.manualClose = true;

    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }

    try {
      state.socket?.close();
    } catch {
      // Ignore close errors.
    }

    state.socket = null;
    this.connections.delete(room);
  }

  send(room: string, message: RealtimeMessage | string | object): void {
    const state = this.connections.get(room);
    if (!state?.socket || state.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const payload = typeof message === 'string' ? message : JSON.stringify(message);
    state.socket.send(payload);
  }

  private ensureRoomState(room: string): RoomConnection {
    let state = this.connections.get(room);
    if (!state) {
      state = {
        subject: new Subject<RealtimeMessage>(),
        socket: null,
        reconnectAttempts: 0,
        reconnectTimer: null,
        manualClose: false,
        subscriberCount: 0
      };
      this.connections.set(room, state);
    }

    state.manualClose = false;
    return state;
  }

  private openSocket(room: string): void {
    const state = this.connections.get(room);
    if (!state || state.socket?.readyState === WebSocket.OPEN || state.socket?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const wsUrl = this.buildSocketUrl(room);
    if (!wsUrl) {
      return;
    }

    const socket = new WebSocket(wsUrl);
    state.socket = socket;

    socket.onopen = () => {
      state.reconnectAttempts = 0;
    };

    socket.onmessage = (event: MessageEvent) => {
      const raw = typeof event.data === 'string' ? event.data : '';

      if (!raw) {
        return;
      }

      try {
        state.subject.next(JSON.parse(raw) as RealtimeMessage);
      } catch {
        state.subject.next({ type: 'message', data: raw });
      }
    };

    socket.onerror = () => {
      // The close handler will manage reconnects.
    };

    socket.onclose = () => {
      state.socket = null;

      if (state.manualClose || state.subscriberCount === 0) {
        return;
      }

      this.scheduleReconnect(room);
    };
  }

  private scheduleReconnect(room: string): void {
    const state = this.connections.get(room);
    if (!state || state.manualClose || state.subscriberCount === 0) {
      return;
    }

    if (state.reconnectTimer) {
      return;
    }

    state.reconnectAttempts += 1;
    const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts - 1), this.maxReconnectDelayMs);

    state.reconnectTimer = setTimeout(() => {
      const currentState = this.connections.get(room);
      if (!currentState || currentState.manualClose || currentState.subscriberCount === 0) {
        return;
      }

      currentState.reconnectTimer = null;
      this.openSocket(room);
    }, delay);
  }

  private buildSocketUrl(room: string): string | null {
    if (!this.isBrowser()) {
      return null;
    }

    const apiUrl = environment.apiBaseUrl.replace(/\/api\/v1\/?$/, '');
    const wsBaseUrl = apiUrl.startsWith('https://')
      ? apiUrl.replace('https://', 'wss://')
      : apiUrl.replace('http://', 'ws://');

    return `${wsBaseUrl}/ws/${encodeURIComponent(room)}`;
  }

  private isBrowser(): boolean {
    return isPlatformBrowser(this.platformId);
  }
}