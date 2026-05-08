import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Invoice, InvoiceListParams, ApiResponse } from '../../shared/models/invoice.model';

@Injectable({
    providedIn: 'root'
})
export class InvoiceService {
    private readonly API = `${environment.apiBaseUrl}/staff/portal/invoices`;

    constructor(private http: HttpClient) { }

    getInvoices(params?: InvoiceListParams): Observable<ApiResponse<Invoice[]>> {
        let httpParams = new HttpParams();

        if (params) {
            if (params.status) {
                httpParams = httpParams.set('status', params.status);
            }
            if (params.search) {
                httpParams = httpParams.set('search', params.search);
            }
            if (params.date_from) {
                httpParams = httpParams.set('date_from', params.date_from);
            }
            if (params.date_to) {
                httpParams = httpParams.set('date_to', params.date_to);
            }
        }

        return this.http.get<ApiResponse<Invoice[]>>(this.API, { params: httpParams });
    }

    getInvoice(id: string): Observable<ApiResponse<Invoice>> {
        return this.http.get<ApiResponse<Invoice>>(`${this.API}/${id}`);
    }

    createInvoice(payload: Partial<Invoice>): Observable<ApiResponse<Invoice>> {
        return this.http.post<ApiResponse<Invoice>>(this.API, payload);
    }

    updateInvoice(id: string, payload: Partial<Invoice>): Observable<ApiResponse<Invoice>> {
        return this.http.put<ApiResponse<Invoice>>(`${this.API}/${id}`, payload);
    }

    updateInvoiceStatus(ids: string[], newStatus: string): Observable<any> {
        const params = new HttpParams().set('new_status', newStatus);
        return this.http.patch<any>(`${this.API}/status`, { ids }, { params });
    }

    deleteInvoice(id: string): Observable<any> {
        return this.http.delete(`${this.API}/${id}`);
    }

    getTrash(hospitalId?: string): Observable<ApiResponse<Invoice[]>> {
        let params = new HttpParams();
        if (hospitalId) {
            params = params.set('hospital_id', hospitalId);
        }
        return this.http.get<ApiResponse<Invoice[]>>(`${this.API}/trash`, { params });
    }

    restoreInvoice(id: string): Observable<any> {
        return this.http.post(`${this.API}/${id}/restore`, {});
    }
}