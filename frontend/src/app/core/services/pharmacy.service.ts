import { Injectable, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { tap, catchError, finalize } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Medicine } from '../../shared/models/medicine.model';

export interface Sale {
  id?: string;
  medicineId?: string;
  medicineName: string;
  salt?: string;
  customer?: string;
  quantity: number;
  unitPrice: number;
  totalAmount: number;
  date: Date;
}

export interface AddMedicineApiRequest {
  product_id: number;
  batch_no: string;
  name: string;
  generic_name: string;
  type: string;
  distributor: string;
  purchase_price: number;
  selling_price: number;
  stock_unit: string;
  quantity: number;
  expiration_date: string;
  category: string;
  sub_category: string;
}

export interface DispenseMedicineRequest {
  patient_id: string;
  doctor_id: string;
  medicines: { product_id: number; quantity: number }[];
}

@Injectable({
  providedIn: 'root'
})
export class PharmacyService {

  private readonly API = `${environment.apiBaseUrl}/public/pharmacy`;

  // ============================================================
  // Signals & Subjects
  // ============================================================

  private medicinesChanged = new BehaviorSubject<boolean>(false);
  public medicinesChanged$ = this.medicinesChanged.asObservable();

  private deletedMedicines: Medicine[] = [];

  private deletedMedicinesSubject =
    new BehaviorSubject<Medicine[]>(this.deletedMedicines);

  public deletedMedicines$ =
    this.deletedMedicinesSubject.asObservable();

  readonly medicines = signal<Medicine[]>([]);
  readonly loading = signal<boolean>(false);

  // ============================================================
  // Sales Data
  // ============================================================

  private sales: Sale[] = [];

  constructor(private http: HttpClient) { }

  // ============================================================
  // Backend API methods
  // ============================================================

  /**
   * Search medicines
   */
  searchMedicineApi(query: string): Observable<any> {

    const params = new HttpParams().set('q', query);

    return this.http.get(
      `${this.API}/search-medicine`,
      { params }
    );
  }

  /**
   * Get all medicines
   */
  getAllMedicinesApi(hospitalId?: string): Observable<any> {

    let params = new HttpParams();

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${this.API}/medicines`,
      { params }
    );
  }

  /**
   * Fetch all medicines
   */
  fetchAllMedicines(hospitalId?: string): Observable<any[]> {

    return new Observable(observer => {

      this.getAllMedicinesApi(hospitalId).subscribe({

        next: (res: any) => {

          const items =
            res?.data ||
            res?.medicines ||
            res?.items ||
            [];

          observer.next(
            Array.isArray(items) ? items : []
          );

          observer.complete();
        },

        error: (err) => observer.error(err)
      });
    });
  }

  /**
   * Add medicine
   */
  addMedicineApi(data: AddMedicineApiRequest): Observable<any> {

    return this.http.post(
      `${this.API}/add-medicine`,
      data
    );
  }

  /**
   * Update medicine
   */
  updateMedicineApi(
    id: string,
    data: Partial<AddMedicineApiRequest>
  ): Observable<any> {

    return this.http.put(
      `${this.API}/medicines/${id}`,
      data
    );
  }

  /**
   * Dispense medicine
   */
  dispenseMedicineApi(
    data: DispenseMedicineRequest
  ): Observable<any> {

    return this.http.post(
      `${this.API}/dispense-medicine`,
      data
    );
  }

  /**
   * Delete pharmacy item
   */
  deletePharmacyItemApi(itemId: string): Observable<any> {

    return this.http.delete(
      `${environment.apiBaseUrl}/staff/pharmacy/items/${itemId}`
    );
  }

  /**
   * Restore medicine
   */
  restoreMedicineApi(itemId: string): Observable<any> {

    return this.http.patch(
      `${environment.apiBaseUrl}/staff/pharmacy/items/${itemId}/restore`,
      {}
    );
  }

  /**
   * Get deleted medicines
   */
  getDeletedMedicinesApi(hospitalId?: string): Observable<any> {

    let params = new HttpParams()
      .set('is_deleted', 'true');

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${environment.apiBaseUrl}/staff/pharmacy/items`,
      { params }
    );
  }

  /**
   * Get medicine by product id
   */
  getMedicineByProductId(productId: number): Observable<any> {

    const params = new HttpParams()
      .set('product_id', productId.toString());

    return this.http.get(
      `${this.API}/medicines`,
      { params }
    );
  }

  // ============================================================
  // Reports API Methods
  // ============================================================

  /**
   * Daily sales report
   */
  getDailySalesReport(hospitalId?: string): Observable<any> {

    let params = new HttpParams();

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${environment.apiBaseUrl}/external/pos/reports/daily-sales`,
      { params }
    );
  }

  /**
   * Inventory turnover report
   */
  getInventoryTurnoverReport(hospitalId?: string): Observable<any> {

    let params = new HttpParams();

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${environment.apiBaseUrl}/external/pos/reports/inventory-turnover`,
      { params }
    );
  }

  /**
   * TOP SELLING PRODUCTS REPORT
   * FIXED METHOD
   */
  getTopSellingProducts(hospitalId?: string): Observable<any> {

    let params = new HttpParams();

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${environment.apiBaseUrl}/external/pos/reports/top-selling-products`,
      { params }
    );
  }

  /**
   * Staff pharmacy items
   */
  getStaffPharmacyItems(
    hospitalId?: string,
    page = 1,
    pageSize = 50
  ): Observable<any> {

    let params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());

    if (hospitalId) {
      params = params.set('hospital_id', hospitalId);
    }

    return this.http.get(
      `${environment.apiBaseUrl}/staff/pharmacy/items`,
      { params }
    );
  }

  // ============================================================
  // Load Medicines
  // ============================================================

  loadMedicinesFromApi(hospitalId?: string): void {

    if (typeof window === 'undefined') {
      return;
    }

    this.loading.set(true);

    this.fetchAllMedicines(hospitalId)
      .pipe(

        tap((items: any[]) => {

          this.medicines.set(
            items.map((m: any) => this.apiToMedicine(m))
          );
        }),

        catchError(err => {

          console.error(
            '[PharmacyService] Failed to load medicines:',
            err
          );

          return of(null);
        }),

        finalize(() => {
          this.loading.set(false);
        })
      )
      .subscribe();
  }

  // ============================================================
  // API → Medicine Mapper
  // ============================================================

  public apiToMedicine(apiMed: any): Medicine {

    return {

      id: apiMed.id ?? '',

      productId:
        (apiMed.product_id ?? '').toString(),

      name: apiMed.name || '',

      salt:
        apiMed.generic_name ||
        apiMed.salt ||
        '',

      genericName:
        apiMed.generic_name || '',

      batchNumber:
        apiMed.batch_no ||
        apiMed.batchNumber ||
        '',

      quantity:
        apiMed.quantity ?? 0,

      purchasedPrice:
        apiMed.purchase_price ?? 0,

      sellingPrice:
        apiMed.selling_price ?? 0,

      manufactureDate: '',

      expiryDate:
        apiMed.expiration_date ||
        apiMed.expiryDate ||
        '',

      supplierName: '',

      distributorName:
        apiMed.distributor ||
        apiMed.distributor_name ||
        apiMed.supplier ||
        '',

      distributorMobile:
        apiMed.distributor_mobile || '',

      distributorCompany:
        apiMed.distributor ||
        apiMed.distributor_name ||
        apiMed.supplier ||
        '',

      type:
        apiMed.type || '',

      category:
        apiMed.category || '',

      subCategory:
        apiMed.sub_category || '',

      stockUnit:
        apiMed.stock_unit || ''
    };
  }

  // ============================================================
  // Legacy Local Methods
  // ============================================================

  restoreMedicine(med: Medicine) {

    this.deletedMedicines =
      this.deletedMedicines.filter(
        m => m.id !== med.id
      );

    this.deletedMedicinesSubject.next([
      ...this.deletedMedicines
    ]);

    const restored = { ...med };

    delete restored.deletedOn;

    this.medicines.update(current => [
      ...current,
      restored
    ]);
  }

  deleteMedicinePermanently(med: Medicine) {

    this.deletedMedicines =
      this.deletedMedicines.filter(
        m => m.id !== med.id
      );

    this.deletedMedicinesSubject.next([
      ...this.deletedMedicines
    ]);
  }

  moveToTrash(med: Medicine) {

    const now = new Date();

    const trashedMed = {
      ...med,
      productId: med.productId ?? med.id,
      deletedOn: now.toISOString()
    };

    this.deletedMedicines.push(trashedMed);

    this.deletedMedicinesSubject.next([
      ...this.deletedMedicines
    ]);

    this.medicines.update(current =>
      current.filter(m => m.id !== med.id)
    );

    this.medicinesChanged.next(true);
  }

  getSales(): Sale[] {
    return this.sales;
  }

  calculateWeeklySales(): number {

    const now = new Date();

    const sevenDaysAgo = new Date(now);

    sevenDaysAgo.setDate(now.getDate() - 7);

    return this.sales
      .filter(
        s => s.date >= sevenDaysAgo &&
          s.date <= now
      )
      .reduce(
        (sum, s) => sum + s.totalAmount,
        0
      );
  }

  calculateMonthlySales(): number {

    const now = new Date();

    const startOfMonth = new Date(
      now.getFullYear(),
      now.getMonth(),
      1
    );

    return this.sales
      .filter(
        s => s.date >= startOfMonth &&
          s.date <= now
      )
      .reduce(
        (sum, s) => sum + s.totalAmount,
        0
      );
  }

  calculateTotalRevenue(): number {

    return this.sales.reduce(
      (sum, s) => sum + s.totalAmount,
      0
    );
  }

  getAll(): Medicine[] {
    return this.medicines();
  }

  getAll$(): Observable<Medicine[]> {
    return of(this.medicines());
  }

  getById(id: string): Medicine | undefined {

    return this.medicines().find(
      m => m.id === id
    );
  }

  add(medicine: Omit<Medicine, 'id'>): Medicine {

    const allIds = [

      ...this.medicines().map(m =>
        parseInt(m.id, 10)
      ),

      ...this.deletedMedicines.map(m =>
        parseInt(m.id, 10)
      )

    ].filter(n => !isNaN(n));

    const nextId =
      allIds.length > 0
        ? Math.max(...allIds) + 1
        : 1;

    const idStr = nextId.toString();

    const newMedicine: Medicine = {
      ...medicine,
      id: idStr,
      productId: idStr
    };

    this.medicines.update(current => [
      ...current,
      newMedicine
    ]);

    this.medicinesChanged.next(true);

    return newMedicine;
  }

  update(
    id: string,
    medicine: Omit<Medicine, 'id'>
  ): Medicine | undefined {

    const index =
      this.medicines().findIndex(
        m => m.id === id
      );

    if (index !== -1) {

      const updatedMedicine: Medicine = {
        ...medicine,
        id
      };

      this.medicines.update(items =>
        items.map(m =>
          m.id === id
            ? updatedMedicine
            : m
        )
      );

      this.medicinesChanged.next(true);

      return updatedMedicine;
    }

    return undefined;
  }

  delete(id: string): boolean {

    const current = this.medicines();

    const index =
      current.findIndex(
        m => m.id === id
      );

    if (index !== -1) {

      const deleted = current[index];

      this.deletedMedicines.push({
        ...deleted,
        deletedOn: new Date().toISOString()
      });

      this.deletedMedicinesSubject.next([
        ...this.deletedMedicines
      ]);

      this.medicines.update(items =>
        items.filter(m => m.id !== id)
      );

      this.medicinesChanged.next(true);

      return true;
    }

    return false;
  }

  getDeletedMedicines(): Medicine[] {
    return this.deletedMedicines;
  }
}