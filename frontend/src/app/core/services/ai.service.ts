import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface AIPredictRequest {
  name: string;
  age: number;
  doctor: string;
  disease_type: string;
}

export interface PredictionRequest {
  [key: string]: any;
}

@Injectable({
  providedIn: 'root'
})
export class AiService {
  private readonly API = `${environment.apiBaseUrl}/ai`;

  constructor(private http: HttpClient) {}

  /** Predict consultation duration (ML model) */
  predict(data: PredictionRequest): Observable<{ [key: string]: number }> {
    return this.http.post<{ [key: string]: number }>(`${this.API}/ml/predict`, data);
  }

  /** Predict wait time */
  predictWaitTime(data: AIPredictRequest): Observable<any> {
    return this.http.post(`${this.API}/core/predict-wait-time`, data);
  }
}
