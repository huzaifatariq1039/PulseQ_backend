import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class SystemService {
  private readonly API = `${environment.apiBaseUrl}/system`;
  private readonly ROOT = environment.apiBaseUrl.replace('/api/v1', '');

  constructor(private http: HttpClient) {}

  /** Health check */
  healthCheck(): Observable<any> {
    return this.http.get(`${this.API}/health`);
  }

  /** Test database connection */
  testDb(): Observable<any> {
    return this.http.get(`${this.API}/test-db`);
  }

  /** Root endpoint (API info) */
  getApiInfo(): Observable<any> {
    return this.http.get(this.ROOT);
  }

  /** Ping endpoint */
  ping(): Observable<any> {
    return this.http.get(`${this.ROOT}/ping`);
  }
}
