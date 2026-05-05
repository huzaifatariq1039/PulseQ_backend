import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class PatientActionsService {
  private readonly API = `${environment.apiBaseUrl}/patient/actions`;

  constructor(private http: HttpClient) { }

  /** Get patient visit history */
  getVisitHistory(options: {
    doctorId?: string; department?: string;
    fromDate?: string; toDate?: string;
    page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.doctorId) params = params.set('doctor_id', options.doctorId);
    if (options.department) params = params.set('department', options.department);
    if (options.fromDate) params = params.set('from_date', options.fromDate);
    if (options.toDate) params = params.set('to_date', options.toDate);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.API}/visit-history`, { params });
  }

  /** Get patient visit detail */
  getVisitDetail(tokenId: string): Observable<any> {
    return this.http.get(`${this.API}/visit/${tokenId}`);
  }
}
