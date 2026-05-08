import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ExternalPosService {
  private readonly API = `${environment.apiBaseUrl}/external/pos`;

  constructor(private http: HttpClient) {}

  // ============================================================
  //  Auth
  // ============================================================

  /** Verify if a user belongs to a specific hospital */
  verifyHospitalUser(data: { user_id: string; hospital_id: string }): Observable<any> {
    return this.http.post(`${this.API}/auth/verify-hospital-user`, data);
  }

  // ============================================================
  //  Patients
  // ============================================================

  /** Sync patient data from external POS/HIS system */
  syncPatient(data: {
    external_id: string; name: string; phone: string;
    email?: string; hospital_id: string; mrn?: string;
  }): Observable<any> {
    return this.http.post(`${this.API}/patients/sync`, data);
  }

  /** Get all patients registered at a specific hospital */
  getHospitalPatients(hospitalId: string): Observable<any> {
    return this.http.get(`${this.API}/patients/${hospitalId}`);
  }

  // ============================================================
  //  Prescriptions
  // ============================================================

  /** Create a digital prescription */
  createPrescription(data: any): Observable<any> {
    return this.http.post(`${this.API}/prescriptions/create`, data);
  }

  /** Get prescription status */
  getPrescriptionStatus(prescriptionId: string): Observable<any> {
    return this.http.get(`${this.API}/prescriptions/${prescriptionId}/status`);
  }

  /** Cancel prescription */
  cancelPrescription(prescriptionId: string): Observable<any> {
    return this.http.put(`${this.API}/prescriptions/${prescriptionId}/cancel`, {});
  }

  // ============================================================
  //  Inventory
  // ============================================================

  /** Check stock */
  checkStock(itemIds: string): Observable<any> {
    const params = new HttpParams().set('item_ids', itemIds);
    return this.http.get(`${this.API}/inventory/check-stock`, { params });
  }

  /** Reserve stock */
  reserveStock(data: any): Observable<any> {
    return this.http.post(`${this.API}/inventory/reserve`, data);
  }

  /** Release stock */
  releaseStock(data: any): Observable<any> {
    return this.http.put(`${this.API}/inventory/release`, data);
  }

  /** Get low stock items */
  getLowStock(): Observable<any> {
    return this.http.get(`${this.API}/inventory/low-stock`);
  }

  // ============================================================
  //  Orders
  // ============================================================

  /** Create order from prescription */
  createOrderFromPrescription(data: {
    prescription_id: string; hospital_id: string; payment_method?: string;
  }): Observable<any> {
    return this.http.post(`${this.API}/orders/create-from-prescription`, data);
  }

  /** Get order status */
  getOrderStatus(orderId: string): Observable<any> {
    return this.http.get(`${this.API}/orders/${orderId}/status`);
  }

  /** Process order payment */
  processOrderPayment(orderId: string, data: {
    amount: number; method: string; transaction_id?: string;
  }): Observable<any> {
    return this.http.post(`${this.API}/orders/${orderId}/payment`, data);
  }

  /** Get pending fulfillment orders */
  getPendingOrders(): Observable<any> {
    return this.http.get(`${this.API}/orders/pending-fulfillment`);
  }

  // ============================================================
  //  Invoices
  // ============================================================

  /** Create insurance invoice */
  createInsuranceInvoice(data: {
    order_id: string; insurance_provider: string;
    policy_number: string; coverage_amount: number;
  }): Observable<any> {
    return this.http.post(`${this.API}/invoices/create-with-insurance`, data);
  }

  /** Get insurance status */
  getInsuranceStatus(invoiceId: string): Observable<any> {
    return this.http.get(`${this.API}/invoices/${invoiceId}/insurance-status`);
  }

  /** Submit insurance claim */
  submitInsuranceClaim(invoiceId: string): Observable<any> {
    return this.http.post(`${this.API}/invoices/${invoiceId}/submit-insurance`, {});
  }

  /** Get patient balance */
  getPatientBalance(patientId: string): Observable<any> {
    return this.http.get(`${this.API}/invoices/patient-balance/${patientId}`);
  }

  // ============================================================
  //  Reports
  // ============================================================

  /** Get daily sales */
  getDailySales(date?: string): Observable<any> {
    let params = new HttpParams();
    if (date) params = params.set('date', date);
    return this.http.get(`${this.API}/reports/daily-sales`, { params });
  }

  /** Get prescription analytics */
  getPrescriptionAnalytics(): Observable<any> {
    return this.http.get(`${this.API}/reports/prescription-analytics`);
  }

  /** Get inventory turnover */
  getInventoryTurnover(): Observable<any> {
    return this.http.get(`${this.API}/reports/inventory-turnover`);
  }

  /** Get revenue by department */
  getRevenueByDepartment(): Observable<any> {
    return this.http.get(`${this.API}/revenue/by-department`);
  }

  // ============================================================
  //  Webhooks
  // ============================================================

  /** Webhook for order status */
  webhookOrderStatus(payload: any): Observable<any> {
    return this.http.post(`${this.API}/webhooks/order-status`, payload);
  }

  /** Webhook for inventory alerts */
  webhookInventoryAlerts(payload: any): Observable<any> {
    return this.http.post(`${this.API}/webhooks/inventory-alerts`, payload);
  }

  // ============================================================
  //  POS Sales & Medicines
  // ============================================================

  /** Create POS sale */
  createPosSale(payload: any): Observable<any> {
    return this.http.post(`${this.API}/sales`, payload);
  }

  /** Get sales history */
  getSalesHistory(hospitalId?: string): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.API}/sales/history`, { params });
  }

  /** Get medicines (POS) */
  getMedicines(search?: string): Observable<any> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    return this.http.get(`${this.API}/medicines`, { params });
  }

  /** Get medicine by barcode */
  getMedicineByBarcode(barcode: string): Observable<any> {
    return this.http.get(`${this.API}/medicines/barcode/${barcode}`);
  }
}
