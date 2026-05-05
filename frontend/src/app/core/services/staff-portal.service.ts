import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class StaffPortalService {
  private readonly API = `${environment.apiBaseUrl}/staff`;
  private readonly PORTAL_API = `${environment.apiBaseUrl}/portal`;

  constructor(private http: HttpClient) { }

  // ============================================================
  //  Consultation
  // ============================================================

  /** Get current patient for a doctor */
  getDoctorCurrentPatient(doctorId: string, hospitalId?: string): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.API}/consultation/doctor/current-patient/${doctorId}`, { params });
  }

  /** Start consultation */
  startConsultation(payload: any): Observable<any> {
    return this.http.post(`${this.API}/consultation/consultation/start`, payload);
  }

  /** End consultation */
  endConsultation(payload: any): Observable<any> {
    return this.http.post(`${this.API}/consultation/consultation/end`, payload);
  }

  // ============================================================
  //  Realtime Notifications
  // ============================================================

  /** Notify a room */
  notifyRoom(room: string, payload: any): Observable<any> {
    return this.http.post(`${this.API}/realtime/notify/${room}`, payload);
  }

  // ============================================================
  //  Portal Items (Inventory)
  // ============================================================

  /** List portal items */
  listItems(options: {
    hospitalId?: string; q?: string;
    page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.hospitalId) params = params.set('hospital_id', options.hospitalId);
    if (options.q) params = params.set('q', options.q);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.API}/portal/items`, { params });
  }

  /** Delete a portal item */
  deleteItem(itemId: string): Observable<any> {
    return this.http.delete(`${this.API}/portal/items/${itemId}`);
  }

  // ============================================================
  //  Portal Notifications
  // ============================================================

  /** List portal notifications */
  listNotifications(unreadOnly = true, limit = 50): Observable<any> {
    const params = new HttpParams()
      .set('unread_only', unreadOnly.toString())
      .set('limit', limit.toString());
    return this.http.get(`${this.API}/portal/notifications`, { params });
  }

  /** Mark notification as read */
  markNotificationRead(notificationId: string): Observable<any> {
    return this.http.post(`${this.API}/portal/notifications/${notificationId}/read`, {});
  }

  // ============================================================
  //  Doctor Portal
  // ============================================================

  /** Get doctor tokens */
  getDoctorTokens(status?: string, page = 1, pageSize = 20): Observable<any> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());
    if (status) params = params.set('status', status);
    return this.http.get(`${this.API}/portal/doctor/tokens`, { params });
  }

  /** Get doctor dashboard */
  getDoctorDashboard(upcomingLimit = 5, skippedLimit = 5): Observable<any> {
    const params = new HttpParams()
      .set('upcoming_limit', upcomingLimit.toString())
      .set('skipped_limit', skippedLimit.toString());
    return this.http.get(`${this.PORTAL_API}/doctor/dashboard`, { params });
  }

  // ============================================================
  //  Admin Portal
  // ============================================================

  /** Get admin dashboard — /api/v1/staff/portal/admin/dashboard */
  getAdminDashboard(hospitalId?: string, logsLimit = 10): Observable<any> {
    let params = new HttpParams().set('logs_limit', logsLimit.toString());
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.API}/portal/admin/dashboard`, { params });
  }

  /** Get completed tokens for admin — /api/v1/portal/doctor/tokens?status=completed */
  /** Get completed consultations — GET /api/v1/portal/completed-consultations */
  getCompletedTokens(page = 1, pageSize = 100): Observable<any> {
    const params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());
    return this.http.get(`${this.PORTAL_API}/completed-consultations`, { params });
  }

  // ============================================================
  //  Receptionist Portal
  // ============================================================

  /** Get receptionist dashboard */
  getReceptionistDashboard(hospitalId: string, doctorId?: string, upcomingLimit = 5): Observable<any> {
    let params = new HttpParams()
      .set('hospital_id', hospitalId)
      .set('upcoming_limit', upcomingLimit.toString());
    if (doctorId) params = params.set('doctor_id', doctorId);
    return this.http.get(`${this.PORTAL_API}/receptionist/dashboard`, { params });
  }

  /** Create walk-in token */
  createWalkinToken(payload: any): Observable<any> {
    return this.http.post(`${this.API}/portal/receptionist/walkin-token`, payload);
  }

  /** Skip a token from the receptionist portal */
  skipToken(tokenId: string): Observable<any> {
    return this.http.post(`${environment.apiBaseUrl}/staff/receptionists/tokens/${tokenId}/skip`, {});
  }

  getDoctorRatings(doctorId: string, page = 1, pageSize = 100): Observable<any> {
    const params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());
    return this.http.get(`${environment.apiBaseUrl}/ratings/doctor/${doctorId}`, { params });
  }

  // ============================================================
  //  Pharmacy Items (Staff)
  // ============================================================

  /** List pharmacy items */
  listPharmacyItems(options: {
    hospitalId?: string; q?: string;
    page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.hospitalId) params = params.set('hospital_id', options.hospitalId);
    if (options.q) params = params.set('q', options.q);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.API}/pharmacy/items`, { params });
  }

  /** Delete pharmacy item */
  deletePharmacyItem(itemId: string): Observable<any> {
    return this.http.delete(`${this.API}/pharmacy/items/${itemId}`);
  }
}
