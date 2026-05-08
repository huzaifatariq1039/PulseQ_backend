import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface PaymentMethod {
  id: string;
  name: string;
  type: string;
  icon?: string;
  enabled: boolean;
}

export interface AppointmentSummary {
  doctor: any;
  hospital: any;
  consultation_fee: number;
  total_amount: number;
  appointment_date: string;
}

export interface PaymentConfirmationRequest {
  token_id: string;
  payment_method: 'cash' | 'card' | 'easypaisa' | 'jazzcash';
  payment_type?: string;
  amount?: number;
  card_details?: {
    card_number: string;
    expiry_month: string;
    expiry_year: string;
    cvv: string;
    cardholder_name: string;
    bank_code?: string;
    bank_name?: string;
  };
  easypaisa_details?: {
    phone_number: string;
    otp?: string;
  };
  notification_types?: ('whatsapp' | 'sms')[];
}

export interface PaymentConfirmationResponse {
  token_id: string;
  payment_id: string;
  status: string;
  transaction_id?: string;
  message: string;
  appointment_summary: AppointmentSummary;
}

export interface PaymentResponse {
  id: string;
  token_id: string;
  user_id: string;
  amount: number;
  payment_method: string;
  status: string;
  transaction_id?: string;
  created_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class PaymentService {
  private readonly API = `${environment.apiBaseUrl}/patient/payments`;

  constructor(private http: HttpClient) {}

  /** Get available payment methods */
  getPaymentMethods(): Observable<any[]> {
    return this.http.get<any[]>(`${this.API}/methods`);
  }

  /** Get appointment summary for payment confirmation */
  getAppointmentSummary(tokenId: string): Observable<AppointmentSummary> {
    return this.http.get<AppointmentSummary>(`${this.API}/token/${tokenId}/summary`);
  }

  /** Confirm payment (process) */
  processPayment(data: PaymentConfirmationRequest): Observable<PaymentConfirmationResponse> {
    return this.http.post<PaymentConfirmationResponse>(`${this.API}/process`, data);
  }

  /** Confirm payment (confirm alias) */
  confirmPayment(data: PaymentConfirmationRequest): Observable<PaymentConfirmationResponse> {
    return this.http.post<PaymentConfirmationResponse>(`${this.API}/confirm`, data);
  }

  /** Get payment history */
  getPaymentHistory(limit = 20): Observable<PaymentResponse[]> {
    const params = new HttpParams().set('limit', limit.toString());
    return this.http.get<PaymentResponse[]>(`${this.API}/history`, { params });
  }

  /** Get specific payment details */
  getPaymentDetails(paymentId: string): Observable<PaymentResponse> {
    return this.http.get<PaymentResponse>(`${this.API}/${paymentId}`);
  }
}
