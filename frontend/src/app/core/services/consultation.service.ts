import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Consultation } from '../../shared/models/consultation.model';
import { QueueService } from './queue.service';
import { Token } from '../../shared/models/token.model';
import { DoctorRating } from '../../shared/models/doctor-rating.model';

@Injectable({
  providedIn: 'root'
})
export class ConsultationService {
  private readonly API = `${environment.apiBaseUrl}/staff/consultation`;
  private readonly RATINGS_CACHE_KEY_PREFIX = 'pulseq_rating_';

  private consultationsSubject = new BehaviorSubject<Consultation[]>([]);
  consultations$ = this.consultationsSubject.asObservable();

  private storageKey = 'pulseq_consultations_v1';

  constructor(
    private http: HttpClient,
    private queueService: QueueService
  ) {
    this.loadFromStorage();
  }

  // ============================================================
  //  Backend API methods
  // ============================================================

  getDoctorCurrentPatient(doctorId: string, hospitalId?: string): Observable<any> {
    const params: any = {};
    if (hospitalId) params.hospital_id = hospitalId;
    return this.http.get(`${this.API}/doctor/current-patient/${doctorId}`, { params });
  }

  startConsultationApi(payload: any): Observable<any> {
    return this.http.post(`${this.API}/start`, payload);
  }

  endConsultationApi(payload: any): Observable<any> {
    return this.http.post(`${this.API}/end`, payload);
  }

  getPatientHistoryApi(patientId: string): Observable<any> {
    return this.http.get(`${this.API}/patient/${patientId}/history`);
  }

  // ============================================================
  //  Legacy local methods (backward compatibility)
  // ============================================================

  private loadFromStorage(): void {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return;
      const raw = window.localStorage.getItem(this.storageKey);
      if (!raw) {
        const mockConsultations: Consultation[] = [
          {
            id: '1',
            patientId: 'patient@example.com',
            patientName: 'John Doe',
            doctorId: 'doc1',
            doctorName: 'Dr. Smith',
            tokenId: 'token1',
            tokenNumber: 'A001',
            reason: 'Fever and cough',
            phone: '123-456-7890',
            notes: 'Prescribed antibiotics',
            startTime: new Date('2023-10-01T10:00:00'),
            endTime: new Date('2023-10-01T10:30:00'),
            rating: { stars: 5, feedback: 'Great doctor', ratedAt: new Date().toISOString() },
            department: 'General Medicine',
            patientAge: 30,
            patientGender: 'Male',
            createdAt: new Date('2023-10-01T09:00:00')
          },
          {
            id: '2',
            patientId: 'patient@example.com',
            patientName: 'John Doe',
            doctorId: 'doc2',
            doctorName: 'Dr. Johnson',
            tokenId: 'token2',
            tokenNumber: 'B002',
            reason: 'Checkup',
            phone: '123-456-7890',
            notes: 'Everything looks good',
            startTime: new Date('2023-09-15T14:00:00'),
            endTime: new Date('2023-09-15T14:20:00'),
            rating: { stars: 4, feedback: 'Good service', ratedAt: new Date().toISOString() },
            department: 'Cardiology',
            patientAge: 30,
            patientGender: 'Male',
            createdAt: new Date('2023-09-15T13:00:00')
          }
        ];
        this.consultationsSubject.next(mockConsultations);
        this.saveToStorage();
        return;
      }
      const parsed = JSON.parse(raw) as any[];
      const revived: Consultation[] = parsed.map(p => ({
        ...p,
        startTime: p.startTime ? new Date(p.startTime) : new Date(),
        endTime: p.endTime ? new Date(p.endTime) : undefined,
        createdAt: p.createdAt ? new Date(p.createdAt) : undefined
      }));
      this.consultationsSubject.next(revived);
    } catch { /* ignore */ }
  }

  private saveToStorage(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(this.storageKey, JSON.stringify(this.consultationsSubject.value));
      }
    } catch { /* ignore */ }
  }

  private generateId(): string {
    return `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  }

  /**
   * ✅ Local start — marks token IN_PROGRESS AND removes it from the queue array
   * so getUpcomingQueue() never returns a serving token.
   */
  startConsultation(tokenId: string): void {
    this.queueService.updateTokenStatus(tokenId, 'IN_PROGRESS');

    const token = this.queueService.getTokenById(tokenId);
    const consultation: Consultation = {
      id: this.generateId(),
      patientId: token ? token.patientId : '',
      patientName: token ? (token as any).patientName : '',
      doctorId: token ? token.doctorId : '',
      doctorName: token ? (token as any).doctor : '',
      tokenId,
      tokenNumber: token ? token.tokenNumber : '',
      reason: token ? (token as any).reasonForVisit : '',
      phone: token ? (token as any).patientPhone : '',
      startTime: new Date(),
    } as Consultation;

    const current = this.consultationsSubject.value;
    this.consultationsSubject.next([...current, consultation]);
    this.saveToStorage();

    // ✅ Remove from local queue so upcoming list updates immediately
    this.queueService.removeToken(tokenId);
  }

  finishConsultation(tokenId: string, notes: string): void {
    const list = this.consultationsSubject.value.map(c => ({ ...c }));
    const idx = list.findIndex(
      c => c.tokenId === tokenId && (!c.endTime || c.endTime <= c.startTime)
    );
    const now = new Date();
    const token = this.queueService.getTokenById(tokenId);

    if (idx !== -1) {
      list[idx].endTime = now;
      list[idx].notes = notes;
      if (!list[idx].patientId && token) list[idx].patientId = token.patientId;
      if (!list[idx].patientName && token) list[idx].patientName = (token as any).patientName;
      if (!list[idx].doctorId && token) list[idx].doctorId = token.doctorId;
      if (!list[idx].doctorName && token) list[idx].doctorName = (token as any).doctor;
      if (!list[idx].reason && token) list[idx].reason = (token as any).reasonForVisit;
      if (!list[idx].phone && token) list[idx].phone = (token as any).patientPhone;
      if (!list[idx].tokenNumber && token) list[idx].tokenNumber = token.tokenNumber;
      if (token) {
        (list[idx] as any).department = token.department;
        (list[idx] as any).patientAge = token.patientAge;
        (list[idx] as any).patientGender = token.patientGender;
        (list[idx] as any).patientCNIC = token.cnic;
        (list[idx] as any).patientMRN = (token as any).mrn;
        (list[idx] as any).createdAt = token.createdAt;
      }
    } else {
      const newConsult: any = {
        id: this.generateId(),
        patientId: token ? token.patientId : '',
        patientName: token ? (token as any).patientName : '',
        doctorId: token ? token.doctorId : '',
        doctorName: token ? (token as any).doctor : '',
        tokenId,
        tokenNumber: token ? token.tokenNumber : '',
        reason: token ? (token as any).reasonForVisit : '',
        phone: token ? (token as any).patientPhone : '',
        startTime: now,
        endTime: now,
        notes
      };
      if (token) {
        newConsult.department = token.department;
        newConsult.patientAge = token.patientAge;
        newConsult.patientGender = token.patientGender;
        newConsult.patientCNIC = token.cnic;
        newConsult.patientMRN = (token as any).mrn;
        newConsult.createdAt = token.createdAt;
      }
      list.push(newConsult as Consultation);
    }

    this.consultationsSubject.next(list);
    this.saveToStorage();
    this.queueService.updateTokenStatus(tokenId, 'DONE');
  }

  getCompletedToday(): number {
    const today = new Date();
    const isSameDay = (d?: Date) =>
      !!d &&
      d.getFullYear() === today.getFullYear() &&
      d.getMonth() === today.getMonth() &&
      d.getDate() === today.getDate();
    return this.consultationsSubject.value.filter(c => isSameDay(c.endTime)).length;
  }

  getPatientHistory(patientId: string): Observable<Consultation[]> {
    return this.consultations$.pipe(
      map(c => c.filter(x => x.patientId === patientId))
    );
  }

  getPatientHistoryByEmail(email: string): Observable<Consultation[]> {
    return this.consultations$.pipe(
      map(c => c.filter(x =>
        x.patientId === email ||
        x.patientName?.toLowerCase().includes(email.split('@')[0]) || false
      ))
    );
  }

  getDoctorHistory(patientId: string, doctorId: string): Observable<Consultation[]> {
    return this.consultations$.pipe(
      map(c => c.filter(x => x.patientId === patientId && x.doctorId === doctorId))
    );
  }

  getGroupedByPatient(): Observable<Map<string, Consultation[]>> {
    return this.consultations$.pipe(
      map(consultations => {
        const grouped = new Map<string, Consultation[]>();
        consultations.forEach(c => {
          if (!grouped.has(c.patientId)) grouped.set(c.patientId, []);
          grouped.get(c.patientId)!.push(c);
        });
        return grouped;
      })
    );
  }

  submitRating(consultationId: string, rating: DoctorRating): Observable<any> {
    this.cacheRating(consultationId, rating);
    return this.http.post(`${environment.apiBaseUrl}/ratings`, {
      token_id: consultationId,
      rating: rating.stars,
      feedback: rating.feedback
    });
  }

  addRatingToConsultation(consultationId: string, rating: any): void {
    const list = this.consultationsSubject.value.map(c => ({ ...c }));
    const idx = list.findIndex(c => c.id === consultationId);
    if (idx !== -1) {
      list[idx].rating = rating;
      this.consultationsSubject.next(list);
      this.saveToStorage();
    }
  }

  private cacheRating(appointmentId: string, rating: DoctorRating): void {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return;
      const ratingData = {
        ...rating,
        ratedAt: rating.ratedAt || new Date().toISOString(),
        cachedAt: new Date().toISOString()
      };
      window.localStorage.setItem(
        `${this.RATINGS_CACHE_KEY_PREFIX}${appointmentId}`,
        JSON.stringify(ratingData)
      );
      console.log(`[Rating Cache] Cached rating for ${appointmentId}:`, ratingData);
    } catch (e) {
      console.warn('[Rating Cache] Failed to cache rating:', e);
    }
  }

  getCachedRating(appointmentId: string): DoctorRating | undefined {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return undefined;
      const cached = window.localStorage.getItem(
        `${this.RATINGS_CACHE_KEY_PREFIX}${appointmentId}`
      );
      if (!cached) return undefined;
      const ratingData = JSON.parse(cached);
      console.log(`[Rating Cache] Retrieved cached rating for ${appointmentId}:`, ratingData);
      return ratingData;
    } catch (e) {
      console.warn('[Rating Cache] Failed to retrieve cached rating:', e);
      return undefined;
    }
  }

  clearCachedRating(appointmentId: string): void {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return;
      window.localStorage.removeItem(`${this.RATINGS_CACHE_KEY_PREFIX}${appointmentId}`);
      console.log(`[Rating Cache] Cleared cached rating for ${appointmentId}`);
    } catch (e) {
      console.warn('[Rating Cache] Failed to clear cached rating:', e);
    }
  }
}