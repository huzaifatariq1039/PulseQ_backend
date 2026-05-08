import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: string;
  createdAt: Date;
  read: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class NotificationService {
  private notificationsSubject = new BehaviorSubject<Notification[]>([]);
  notifications$ = this.notificationsSubject.asObservable();

  private generateId(): string {
    return `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  }

  sendTokenCreated(tokenDisplayCode: string): void {
    const n: Notification = {
      id: this.generateId(),
      title: 'Token Generated',
      message: `Your token ${tokenDisplayCode} has been successfully created.`,
      type: 'TOKEN_CREATED',
      createdAt: new Date(),
      read: false
    };
    this.notificationsSubject.next([n, ...this.notificationsSubject.value]);
  }

  sendTokenCancelled(tokenDisplayCode: string): void {
    const n: Notification = {
      id: this.generateId(),
      title: 'Token Cancelled',
      message: `Your token ${tokenDisplayCode} has been successfully cancelled.`,
      type: 'TOKEN_CANCELLED',
      createdAt: new Date(),
      read: false
    };
    this.notificationsSubject.next([n, ...this.notificationsSubject.value]);
  }

  sendTokenSkipped(tokenDisplayCode: string, skippedBy: string = 'doctor'): void {
    const n: Notification = {
      id: this.generateId(),
      title: 'Token Skipped',
      message: `Your token ${tokenDisplayCode} has been skipped by ${skippedBy}.`,
      type: 'TOKEN_SKIPPED',
      createdAt: new Date(),
      read: false
    };
    this.notificationsSubject.next([n, ...this.notificationsSubject.value]);
  }

  markAsRead(notificationId: string): void {
    const updated = this.notificationsSubject.value.map(n =>
      n.id === notificationId ? { ...n, read: true } : n
    );
    this.notificationsSubject.next(updated);
  }

  markAllRead(): void {
    const updated = this.notificationsSubject.value.map(n => ({ ...n, read: true }));
    this.notificationsSubject.next(updated);
  }

  getUnreadCount(): number {
    return this.notificationsSubject.value.filter(n => !n.read).length;
  }

  clearAll(): void {
    this.notificationsSubject.next([]);
  }
}