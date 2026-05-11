import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface ReceptionistCreate {
  name: string;
  email: string;
  phone: string;
  password: string;
  hospital_id: string;
}

export interface ReceptionistResponse {
  id: string;
  name: string;
  email: string;
  phone: string;
  hospital_id: string;
  role: string;
  created_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class ReceptionService {
  private readonly API = `${environment.apiBaseUrl}/external/reception`;
  private readonly STAFF_RECEPTION_API = `${environment.apiBaseUrl}/staff/receptionists`;
  private readonly STAFF_PORTAL_API = `${environment.apiBaseUrl}/staff/portal/receptionist`;


  constructor(private http: HttpClient) { }

  /** Create a new receptionist (Admin only) */
  createReceptionist(data: ReceptionistCreate): Observable<ReceptionistResponse> {
    return this.http.post<ReceptionistResponse>(`${this.API}/receptionists`, data);
  }

  /** Get reception queue */
  getQueue(hospitalId: string, options: {
    doctorId?: string; page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams().set('hospital_id', hospitalId);
    if (options.doctorId) params = params.set('doctor_id', options.doctorId);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.API}/queue`, { params });


  }

  /** Get reception tokens */
  getTokens(hospitalId: string, options: {
    doctorId?: string; page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams().set('hospital_id', hospitalId);
    if (options.doctorId) params = params.set('doctor_id', options.doctorId);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.API}/tokens`, { params });
  }

  /** Update an existing receptionist token */
  updateToken(tokenId: string, data: any): Observable<any> {
    return this.http.patch(`${this.STAFF_PORTAL_API}/tokens/${tokenId}`, data);
  }

  /** Delete a receptionist token */
  deleteToken(tokenId: string): Observable<any> {
    return this.http.delete(`${this.STAFF_PORTAL_API}/tokens/${tokenId}`);
  }

  /** Update receptionist token status */
  updateTokenStatus(tokenId: string, status: string): Observable<any> {
    return this.http.patch(`${this.STAFF_PORTAL_API}/tokens/${tokenId}`, { status });
  }

  /** Re-add skipped token via receptionist portal */
  reAddToken(tokenId: string): Observable<any> {
    return this.http.patch(`${this.STAFF_PORTAL_API}/tokens/${tokenId}`, { status: 'WAITING' });
  }

  /** Skip a token (receptionist) */
  skipToken(tokenId: string): Observable<any> {
    return this.http.post(`${this.STAFF_PORTAL_API}/tokens/${tokenId}/skip`, {});
  }

  /** Update doctor queue management info**/
  updateDoctor(doctorId: string, data: any): Observable<any> {
    return this.http.patch(`${environment.apiBaseUrl}/staff/doctors/${doctorId}`, data);
  }

  /** Trigger this when the receptionist clicks 'Submit' on the Walk-in Modal */
  createWalkInToken(
    hospitalId: string,
    doctorId: string,
    patientName: string,
    phone: string,
    age: string,
    gender: string,
    reason: string
  ): Observable<any> {
    const payload: any = {
      hospital_id: hospitalId,
      patient_name: patientName,
      phone: phone,
      age: age,
      gender: gender,
      reason: reason
    };
    if (doctorId) {
      payload.doctor_id = doctorId;
    }
    console.log('Sending walkin token payload:', payload);
    return this.http.post(`${environment.apiBaseUrl}/staff/portal/receptionist/walkin-token`, payload);
  }
}