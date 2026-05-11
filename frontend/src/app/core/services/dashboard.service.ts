import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface UserStatistics {
  total_appointments: number;
  completed_appointments: number;
  cancelled_appointments: number;
  total_spent: number;
}

export interface ActivityLog {
  id: string;
  user_id: string;
  activity_type: string;
  description: string;
  metadata?: any;
  created_at: string;
}

export interface QuickAction {
  id: string;
  action_type: string;
  label: string;
  icon?: string;
  is_enabled: boolean;
}

export interface AppointmentHistory {
  id: string;
  doctor_name: string;
  doctor_specialization: string;
  hospital_name: string;
  appointment_date: string;
  status: string;
  rating?: number;
  token_number: string;
}

@Injectable({
  providedIn: 'root'
})
export class DashboardService {
  private readonly API = `${environment.apiBaseUrl}/patient/dashboard`;

  constructor(private http: HttpClient) {}

  /** Get complete dashboard data */
  getDashboardData(): Observable<any> {
    return this.http.get(this.API);
  }

  /** Get active token overview for dashboard tiles */
  getActiveOverview(): Observable<any> {
    return this.http.get(`${this.API}/active-overview`);
  }

  /** Get active token */
  getActiveToken(): Observable<any> {
    return this.http.get(`${this.API}/active-token`);
  }

  /** Get user statistics */
  getStatistics(): Observable<UserStatistics> {
    return this.http.get<UserStatistics>(`${this.API}/statistics`);
  }

  /** Get user activities */
  getActivities(limit = 10, activityType?: string): Observable<ActivityLog[]> {
    let params = new HttpParams().set('limit', limit.toString());
    if (activityType) params = params.set('activity_type', activityType);
    return this.http.get<ActivityLog[]>(`${this.API}/activities`, { params });
  }

  /** Create activity log */
  createActivity(data: { activity_type: string; description: string; metadata?: any }): Observable<ActivityLog> {
    return this.http.post<ActivityLog>(`${this.API}/activities`, data);
  }

  /** Get quick actions */
  getQuickActions(): Observable<QuickAction[]> {
    return this.http.get<QuickAction[]>(`${this.API}/quick-actions`);
  }

  /** Create quick action */
  createQuickAction(data: any): Observable<QuickAction> {
    return this.http.post<QuickAction>(`${this.API}/quick-actions`, data);
  }

  /** Update quick action */
  updateQuickAction(actionId: string, isEnabled: boolean): Observable<any> {
    const params = new HttpParams().set('is_enabled', isEnabled.toString());
    return this.http.put(`${this.API}/quick-actions/${actionId}`, null, { params });
  }

  /** Get recent tokens */
  getRecentTokens(limit = 5): Observable<any> {
    const params = new HttpParams().set('limit', limit.toString());
    return this.http.get(`${this.API}/recent-tokens`, { params });
  }

  /** Get nearby hospitals for dashboard */
  getNearbyHospitals(options: {
    lat?: number; lng?: number; radiusKm?: number;
    limit?: number; city?: string;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.lat !== undefined) params = params.set('lat', options.lat.toString());
    if (options.lng !== undefined) params = params.set('lng', options.lng.toString());
    if (options.radiusKm) params = params.set('radius_km', options.radiusKm.toString());
    if (options.limit) params = params.set('limit', options.limit.toString());
    if (options.city) params = params.set('city', options.city);
    return this.http.get(`${this.API}/nearby-hospitals`, { params });
  }

  /** Get unified nearby hospitals for dashboard */
  getNearbyHospitalsUnified(options: {
    lat?: number; lng?: number; radiusKm?: number;
    limit?: number; city?: string;
    includeDb?: boolean; includeOsm?: boolean;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.lat !== undefined) params = params.set('lat', options.lat.toString());
    if (options.lng !== undefined) params = params.set('lng', options.lng.toString());
    if (options.radiusKm) params = params.set('radius_km', options.radiusKm.toString());
    if (options.limit) params = params.set('limit', options.limit.toString());
    if (options.city) params = params.set('city', options.city);
    if (options.includeDb !== undefined) params = params.set('include_db', options.includeDb.toString());
    if (options.includeOsm !== undefined) params = params.set('include_osm', options.includeOsm.toString());
    return this.http.get(`${this.API}/nearby-hospitals-unified`, { params });
  }
}
