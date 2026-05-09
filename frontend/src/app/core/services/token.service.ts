import { Injectable } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface SmartTokenGenerateRequest {
  doctor_id: string;
  hospital_id: string;
  appointment_date?: string;
  reason_for_visit?: string;
  patient_name?: string;
  patient_phone?: string;
}

export interface SmartTokenResponse {
  is_active: boolean;
  id: string;
  token_number?: number;
  display_code?: string;
  doctor_id: string;
  hospital_id: string;
  patient_id: string;
  status: string;
  appointment_date?: string;
  queue_position?: number;
  estimated_wait_minutes?: number;
  consultation_fee?: number;
  session_fee?: number;
  payment_status?: string;
  created_at?: string;


  doctor_name?: string;
  doctor_specialization?: string;
  department?: string;
  patient_name?: string;
  patient_phone?: string;
  hospital_name?: string;
}

export interface CancellationResponse {
  message: string;
  token_id: string;
  cancellation_reason: string;
  refund_info?: any;
  refund_id?: string;
}

export interface TokenCreateSpec {
  doctor_id: string;
  hospital_id: string;
  appointment_date: string;
}

@Injectable({
  providedIn: 'root'
})
export class TokenService {
  private readonly API = `${environment.apiBaseUrl}/patient/tokens`;

  constructor(private http: HttpClient) { }

  /** Generate a smart token */
  generateToken(data: SmartTokenGenerateRequest, options?: {
    fingerprintName?: string; fingerprintPhone?: string;
    includeConsultationFee?: boolean; includeSessionFee?: boolean;
  }): Observable<SmartTokenResponse> {
    let params = new HttpParams();
    if (options?.fingerprintName) params = params.set('fingerprint_name', options.fingerprintName);
    if (options?.fingerprintPhone) params = params.set('fingerprint_phone', options.fingerprintPhone);
    if (options?.includeConsultationFee !== undefined) params = params.set('include_consultation_fee', options.includeConsultationFee.toString());
    if (options?.includeSessionFee !== undefined) params = params.set('include_session_fee', options.includeSessionFee.toString());
    return this.http.post<SmartTokenResponse>(`${this.API}/generate`, data, { params });
  }

  /** Generate a smart token with details */
  generateTokenWithDetails(data: SmartTokenGenerateRequest, options?: {
    fingerprintName?: string; fingerprintPhone?: string;
  }): Observable<any> {
    let params = new HttpParams();
    if (options?.fingerprintName) params = params.set('fingerprint_name', options.fingerprintName);
    if (options?.fingerprintPhone) params = params.set('fingerprint_phone', options.fingerprintPhone);
    return this.http.post(`${this.API}/generate`, data, { params });
  }

  /** Generate token by selection */
  generateTokenBySelection(payload: any): Observable<any> {
    return this.http.post(`${this.API}/generate/by-selection`, payload);
  }

  /** Get token generation form data */
  getTokenFormData(hospitalId?: string, department?: string): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    if (department) params = params.set('department', department);
    return this.http.get(`${this.API}/generate/form-data`, { params });
  }

  /** Create a token atomically */
  createToken(data: TokenCreateSpec): Observable<any> {
    return this.http.post(this.API, data);
  }

  /** Create token with Idempotency-Key header */
  createTokenIdempotent(data: { doctor_id: string; hospital_id: string; appointment_date: string }, idempotencyKey: string): Observable<any> {
    const headers = new HttpHeaders().set('Idempotency-Key', idempotencyKey);
    return this.http.post(`${this.API}/secure/tokens/create-idempotent`, data, { headers });
  }

  /** Cancel a token */
  cancelToken(tokenId: string, payload: any = {}): Observable<CancellationResponse> {
    return this.http.post<CancellationResponse>(`${this.API}/${tokenId}/cancel`, payload);
  }

  /** Cancel token (DELETE variant) */
  cancelTokenDelete(tokenId: string, payload: any = {}): Observable<CancellationResponse> {
    return this.http.delete<CancellationResponse>(`${this.API}/${tokenId}/cancel`, { body: payload });
  }

  /** Cancel token (alias POST) */
  cancelTokenAlias(payload: any): Observable<CancellationResponse> {
    return this.http.post<CancellationResponse>(`${this.API}/cancel`, payload);
  }

  /** Get my tokens */
  getMyTokens(onlyActive = true, includeSkipped = true): Observable<any> {
    let params = new HttpParams()
      .set('only_active', onlyActive.toString())
      .set('include_skipped', includeSkipped.toString());
    return this.http.get<any>(`${this.API}/my-tokens`, { params });
  }

  /** Get my upcoming tokens */
  getMyUpcomingTokens(limit = 50): Observable<any> {
    const params = new HttpParams().set('limit', limit.toString());
    return this.http.get(`${this.API}/my-upcoming`, { params });
  }

  /** Get my active token */
  getMyActiveToken(): Observable<SmartTokenResponse> {
    return this.http.get<SmartTokenResponse>(`${this.API}/my-active`);
  }

  /** Get my active token details */
  getMyActiveTokenDetails(): Observable<any> {
    return this.http.get(`${this.API}/my-active-details`);
    // return this.http.get(`/api/v1/patient/tokens/my-active-details`)
  }

  /** Get token history */
  getTokenHistory(): Observable<SmartTokenResponse[]> {
    return this.http.get<SmartTokenResponse[]>(`${this.API}/history`);
  }

  /** Get appointment details for a token */
  getAppointmentDetails(tokenId: string): Observable<any> {
    return this.http.get(`${this.API}/${tokenId}/appointment-details`);
  }

  /** Get token queue status */
  getTokenQueueStatus(tokenId: string): Observable<any> {
    return this.http.get(`${this.API}/${tokenId}/queue-status`);
  }

  /** Process payment for a token */
  processTokenPayment(tokenId: string, paymentData: any): Observable<any> {
    return this.http.post(`${this.API}/${tokenId}/payment`, paymentData);
  }

  /** Get tokens for a hospital */
  getHospitalTokens(hospitalId: string): Observable<any> {
    return this.http.get(`${this.API}/hospital/${hospitalId}`);
  }

  /** Update token status */
  updateTokenStatus(tokenId: string, statusData: any): Observable<any> {
    return this.http.patch(`${this.API}/update-status/${tokenId}`, statusData);
  }

  /** Notify appointment summary */
  notifyAppointmentSummary(tokenId: string): Observable<any> {
    return this.http.post(`${this.API}/${tokenId}/notify/summary`, {});
  }

  /** Send token notifications */
  sendTokenNotifications(tokenId: string, notificationData: {
    token_id: string;
    notification_types: ('whatsapp' | 'sms')[];
    message: string;
    phone_number: string;
  }): Observable<any> {
    return this.http.post(`${this.API}/${tokenId}/notifications`, notificationData);
  }

  /** Get patient visit history */
  getVisitHistory(page = 1, pageSize = 20): Observable<any> {
    const params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());
    return this.http.get(`${environment.apiBaseUrl}/patient/actions/visit-history`, { params });
  }

  /** List tokens with pagination and filters */
  listTokens(options: {
    status?: string; department?: string;
    doctorId?: string; page?: number; limit?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.status) params = params.set('status', options.status);
    if (options.department) params = params.set('department', options.department);
    if (options.doctorId) params = params.set('doctorId', options.doctorId);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.limit) params = params.set('limit', options.limit.toString());
    return this.http.get(`${this.API}/list`, { params });
  }
}
