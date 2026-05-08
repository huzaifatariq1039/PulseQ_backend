import { Injectable } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Token as TokenModel } from '../../shared/models/token.model';
export type Token = TokenModel;

export interface QueueResponse {
  doctor_id: string;
  total_in_queue: number;
  current_serving?: number;
  estimated_wait_minutes: number;
  status: string;
  patients?: any[];
}

@Injectable({
  providedIn: 'root'
})
export class QueueService {
  private readonly API = `${environment.apiBaseUrl}/patient/queue`;
  private readonly CONSULTATION_API = `${environment.apiBaseUrl}/staff/consultation`;

  private activeTokenSubject = new BehaviorSubject<Token | null>(null);
  public activeToken$ = this.activeTokenSubject.asObservable();
  private queueSubject = new BehaviorSubject<Token[]>([]);
  queue$ = this.queueSubject.asObservable();

  constructor(private http: HttpClient) {
    this.loadFromStorage();
  }

  // ============================================================
  //  Backend API methods
  // ============================================================

  getDoctorQueueApi(doctorId: string, appointmentDate?: string, tokenNumber?: number): Observable<QueueResponse> {
    let params = new HttpParams();
    if (appointmentDate) params = params.set('appointment_date', appointmentDate);
    if (tokenNumber !== undefined) params = params.set('token_number', tokenNumber.toString());
    return this.http.get<QueueResponse>(`${this.API}/doctor/${doctorId}`, { params });
  }

  getMyQueuePosition(): Observable<any> {
    return this.http.get(`${this.API}/my-position`);
  }

  getQueueSnapshotApi(room: string): Observable<any> {
    return this.http.get(`${this.API}/snapshot/${room}`);
  }

  testAdvanceQueue(doctorId: string): Observable<any> {
    const params = new HttpParams().set('doctor_id', doctorId);
    return this.http.post(`${this.API}/test/advance`, null, { params });
  }

  advanceQueue(doctorId: string): Observable<any> {
    return this.http.post(`${this.API}/${doctorId}/advance-queue`, {});
  }

  advanceQueueAlt(doctorId: string): Observable<any> {
    return this.http.post(`${this.API}/${doctorId}/advance`, {});
  }

  advanceQueueIdempotent(doctorId: string, idempotencyKey?: string): Observable<any> {
    let headers = new HttpHeaders();
    if (idempotencyKey) headers = headers.set('Idempotency-Key', idempotencyKey);
    return this.http.post(`${this.API}/doctor/${doctorId}/advance-idempotent`, {}, { headers });
  }

  startConsultationApi(tokenId: string): Observable<any> {
    return this.http.post(`${this.API}/token/${tokenId}/start`, {});
  }

  startConsultationIdempotent(tokenId: string): Observable<any> {
    return this.http.post(`${this.API}/token/${tokenId}/start-idempotent`, {});
  }

  skipPatient(tokenId: string): Observable<any> {
    return this.http.post(`${this.CONSULTATION_API}/skip/${tokenId}`, {});
  }

  reAddToQueue(tokenId: string): Observable<any> {
    return this.http.post(`${this.CONSULTATION_API}/re-add/${tokenId}`, {});
  }

  skipPatientIdempotent(tokenId: string): Observable<any> {
    return this.http.post(`${this.API}/token/${tokenId}/skip-idempotent`, {});
  }

  completeConsultationApi(tokenId: string, payload?: any): Observable<any> {
    return this.http.post(`${this.API}/token/${tokenId}/complete`, payload || {});
  }

  // ============================================================
  //  Advanced Queue Operations
  // ============================================================

  advancedAddToQueue(payload: any): Observable<any> {
    return this.http.post(`${this.API}/advanced/add`, payload);
  }

  advancedCallNext(doctorId: string): Observable<any> {
    return this.http.post(`${this.API}/advanced/call-next/${doctorId}`, {});
  }

  advancedComplete(queueId: string): Observable<any> {
    return this.http.post(`${this.API}/advanced/complete/${queueId}`, {});
  }

  advancedRejoin(payload: any): Observable<any> {
    return this.http.post(`${this.API}/advanced/rejoin`, payload);
  }

  advancedPause(doctorId: string, payload?: any): Observable<any> {
    return this.http.post(`${this.API}/advanced/pause/${doctorId}`, payload || {});
  }

  advancedResume(doctorId: string): Observable<any> {
    return this.http.post(`${this.API}/advanced/resume/${doctorId}`, {});
  }

  advancedRecalculate(doctorId: string, payload?: any): Observable<any> {
    return this.http.post(`${this.API}/advanced/recalculate/${doctorId}`, payload || {});
  }

  // ============================================================
  //  Local queue observables
  // ============================================================

  /** All tokens in queue */
  getQueue(): Observable<Token[]> {
    return this.queue$;
  }

  /**
   * ✅ Upcoming queue — WAITING only, excludes IN_PROGRESS / DONE / SKIPPED tokens.
   * Use this everywhere you render the upcoming patients list.
   */
  getUpcomingQueue(): Observable<Token[]> {
    return this.queue$.pipe(
      map(tokens => tokens.filter(t => t.status === 'WAITING'))
    );
  }

  /**
   * ✅ Skipped queue — SKIPPED tokens only.
   */
  getSkippedQueue(): Observable<Token[]> {
    return this.queue$.pipe(
      map(tokens => tokens.filter(t => t.status === 'SKIPPED'))
    );
  }

  // ============================================================
  //  Legacy local methods (backward compatibility)
  // ============================================================

  private loadFromStorage(): void {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return;
      const raw = window.localStorage.getItem('pulseq_queue_v1');
      if (!raw) return;
      const parsed = JSON.parse(raw) as any[];
      const revived: Token[] = parsed.map(p => ({
        ...p,
        createdAt: p.createdAt ? new Date(p.createdAt) : new Date(),
        startTime: p.startTime ? new Date(p.startTime) : undefined,
        endTime: p.endTime ? new Date(p.endTime) : undefined
      }));
      this.queueSubject.next(revived);
    } catch { /* ignore */ }
  }

  private saveToStorage(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem('pulseq_queue_v1', JSON.stringify(this.queueSubject.value));
      }
    } catch { /* ignore */ }
  }

  addToken(token: Token): void {
    const item: Token = {
      ...token,
      createdAt: token.createdAt || new Date(),
      status: token.status || 'WAITING'
    } as Token;
    const current = this.queueSubject.value;
    this.queueSubject.next([...current, item]);
    this.activeTokenSubject.next(item);
    this.saveToStorage();
  }

  addTokenFor(patientId: string, doctorId: string | null, department: string, extras?: Partial<Token>): Token {
    const now = new Date();
    const tokenNumber = this.generateTokenNumber();
    const id = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    const item: Token = {
      id,
      tokenNumber,
      patientId,
      doctorId: doctorId || '',
      department,
      status: 'WAITING',
      createdAt: now,
      ...extras
    } as Token;
    const current = this.queueSubject.value;
    this.queueSubject.next([...current, item]);
    this.activeTokenSubject.next(item);
    this.saveToStorage();
    return item;
  }

  updateTokenStatus(tokenId: string, status: Token['status']): void {
    const updated = this.queueSubject.value.map(t => {
      if (t.id === tokenId) {
        const copy: Token = { ...t, status };
        if (status === 'IN_PROGRESS') copy.startTime = copy.startTime || new Date();
        if (status === 'DONE') copy.endTime = copy.endTime || new Date();
        return copy;
      }
      return t;
    });
    this.queueSubject.next(updated);
    this.saveToStorage();
    const active = this.activeTokenSubject.value;
    if (active && active.id === tokenId) {
      this.activeTokenSubject.next(updated.find(u => u.id === tokenId) || null);
    }
  }

  updateToken(token: Token): void {
    const updated = this.queueSubject.value.map(t => t.id === token.id ? { ...t, ...token } : t);
    this.queueSubject.next(updated);
    this.saveToStorage();
    const active = this.activeTokenSubject.value;
    if (active && active.id === token.id) {
      this.activeTokenSubject.next(updated.find(u => u.id === token.id) || null);
    }
  }

  removeToken(tokenId: string): void {
    const filtered = this.queueSubject.value.filter(t => t.id !== tokenId);
    this.queueSubject.next(filtered);
    this.saveToStorage();
    const active = this.activeTokenSubject.value;
    if (active && active.id === tokenId) {
      this.activeTokenSubject.next(null);
    }
  }

  createToken(token: Token): Token {
    this.addToken(token);
    this.activeTokenSubject.next(token);
    return this.activeTokenSubject.value!;
  }

  deleteToken(): void {
    const active = this.activeTokenSubject.value;
    if (active) {
      this.removeToken(active.id);
    }
    this.activeTokenSubject.next(null);
  }

  generateTokenNumber(): string {
    const existing = this.queueSubject.value.map(t => t.tokenNumber).filter(Boolean) as string[];
    const numbers = existing.map(n => {
      const m = n.match(/A-(\d+)/i);
      return m ? parseInt(m[1], 10) : 0;
    });
    const max = numbers.length ? Math.max(...numbers) : 0;
    return `A-${String(max + 1).padStart(3, '0')}`;
  }

  getCurrentlyServing(doctorId: string): Token | null {
    return this.queueSubject.value.find(
      t => t.doctorId === doctorId && t.status === 'IN_PROGRESS'
    ) || null;
  }

  getWaitingCount(): number {
    return this.queueSubject.value.filter(t => t.status === 'WAITING').length;
  }

  getTokenById(tokenId: string): Token | undefined {
    return this.queueSubject.value.find(t => t.id === tokenId);
  }

  getQueueSnapshot(): Token[] {
    return this.queueSubject.value;
  }
}