import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { Doctor } from '../../shared/models/doctor.model';

export interface DoctorApiResponse {
  id: string;
  name: string;
  department: string;
  subcategory?: string;
  hospital_id: string;
  phone: string;
  email?: string;
  experience_years: number;
  rating?: number;
  review_count?: number;
  consultation_fee: number;
  session_fee?: number;
  has_session?: boolean;
  pricing_type?: string;
  status?: 'available' | 'busy' | 'offline' | 'on_leave';
  available_days?: string[];
  start_time: string;
  end_time: string;
  avatar_initials?: string;
  patients_per_day?: number;
  user_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface DoctorCreateRequest {
  name: string;
  department: string;
  subcategory?: string;
  hospital_id: string;
  phone: string;
  email: string;
  experience_years: number;
  consultation_fee: number;
  session_fee?: number;
  has_session?: boolean;
  pricing_type?: string;
  status?: string;
  available_days?: string[];
  start_time: string;
  end_time: string;
  avatar_initials?: string;
  patients_per_day?: number;
  password: string;
  rating?: number;
  review_count?: number;
}

export interface QueueStatus {
  doctor_id: string;
  total_in_queue: number;
  current_serving?: number;
  estimated_wait_minutes: number;
  status: string;
}

export interface DoctorWithQueue {
  doctor: DoctorApiResponse;
  queue: QueueStatus;
}

export interface DoctorSearchResponse {
  doctors: DoctorWithQueue[];
  total_found: number;
  hospital_id: string;
  category?: string;
  subcategories?: string[];
}

@Injectable({
  providedIn: 'root'
})
export class DoctorService {

  private readonly API = `${environment.apiBaseUrl}/public/doctors`;

  // Department list endpoint is /list, CRUD stays at base
  private readonly DEPARTMENT_API = `${environment.apiBaseUrl}/staff/doctors/departments`;
  private readonly DEPARTMENT_LIST_API = `${environment.apiBaseUrl}/staff/doctors/departments/list`;

  private readonly ADMIN_API = `${environment.apiBaseUrl}/doctors`;

  private doctorsSubject = new BehaviorSubject<Doctor[]>([]);
  public doctors$ = this.doctorsSubject.asObservable();

  constructor(private http: HttpClient) { }

  /** List all doctors with optional filtering */
  listDoctors(options: {
    hospitalId?: string; specialization?: string;
    subcategory?: string; page?: number; limit?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.hospitalId) params = params.set('hospital_id', options.hospitalId);
    if (options.specialization) params = params.set('specialization', options.specialization);
    if (options.subcategory) params = params.set('subcategory', options.subcategory);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.limit) params = params.set('limit', options.limit.toString());
    return this.http.get(`${this.API}`, { params });
  }

  /** Get doctor by ID */
  getDoctor(doctorId: string): Observable<DoctorApiResponse> {
    return this.http.get<DoctorApiResponse>(`${this.API}/${doctorId}`);
  }

  /** Get doctor details (extended info) */
  getDoctorDetails(doctorId: string): Observable<any> {
    return this.http.get(`${this.API}/${doctorId}/details`);
  }

  /** Create a new doctor (Admin only) */
  createDoctor(data: DoctorCreateRequest): Observable<DoctorApiResponse> {
    return this.http.post<DoctorApiResponse>(`${this.ADMIN_API}/`, data);
  }

  /** Update a doctor (Receptionist) */
  updateDoctorApi(doctorId: string, data: any): Observable<any> {
    return this.http.patch(`${this.ADMIN_API}/${doctorId}`, data);
  }

  /** Update doctor status */
  updateDoctorStatus(payload: any): Observable<any> {
    return this.http.patch(`${this.ADMIN_API}/status`, payload);
  }

  /** Delete a doctor (Admin only) */
  deleteDoctorApi(doctorId: string): Observable<any> {
    return this.http.delete(`${this.ADMIN_API}/${doctorId}`);
  }

  /** Get doctors for a specific hospital */
  getDoctorsByHospital(hospitalId: string, category?: string, subcategory?: string, limit = 20): Observable<DoctorSearchResponse> {
    let params = new HttpParams().set('limit', limit.toString());
    if (category) params = params.set('category', category);
    if (subcategory) params = params.set('subcategory', subcategory);
    return this.http.get<DoctorSearchResponse>(`${this.API}/hospital/${hospitalId}`, { params });
  }

  /** Search doctors by name, specialization, or subcategory */
  searchDoctors(query: string, options: {
    hospitalId?: string; category?: string;
    subcategory?: string; limit?: number;
  } = {}): Observable<DoctorSearchResponse> {
    let params = new HttpParams().set('query', query);
    if (options.hospitalId) params = params.set('hospital_id', options.hospitalId);
    if (options.category) params = params.set('category', options.category);
    if (options.subcategory) params = params.set('subcategory', options.subcategory);
    if (options.limit) params = params.set('limit', options.limit.toString());
    return this.http.get<DoctorSearchResponse>(`${this.API}/search`, { params });
  }

  /** Get organized doctor categories with subcategories */
  getDoctorCategories(): Observable<any> {
    return this.http.get(`${this.API}/categories`);
  }

  /** Get subcategories for a main category */
  getSubcategories(mainCategory: string, hospitalId?: string): Observable<any> {
    let params = new HttpParams().set('main_category', mainCategory);
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.API}/subcategories`, { params });
  }

  /** Get doctors by main category */
  getDoctorsByMainCategory(mainCategory: string, hospitalId?: string, subcategory?: string, limit = 20): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    if (subcategory) params = params.set('subcategory', subcategory);
    if (limit) params = params.set('limit', limit.toString());
    return this.http.get(`${this.API}/by-category/${mainCategory}`, { params });
  }

  /** Get doctor availability schedule */
  getDoctorAvailability(doctorId: string): Observable<any> {
    return this.http.get(`${this.API}/${doctorId}/availability`);
  }

  /** Get doctor availability for today */
  getDoctorAvailabilityToday(doctorId: string): Observable<any> {
    return this.http.get(`${this.API}/${doctorId}/availability/today`);
  }

  /** Get available slots for a doctor on a specific day */
  getAvailableSlots(doctorId: string, day: string, slotMinutes = 15): Observable<any> {
    const params = new HttpParams()
      .set('day', day)
      .set('slot_minutes', slotMinutes.toString());
    return this.http.get(`${this.API}/${doctorId}/available-slots`, { params });
  }

  /** Get current queue status for a doctor */
  getDoctorQueueStatus(doctorId: string): Observable<QueueStatus> {
    return this.http.get<QueueStatus>(`${this.API}/${doctorId}/queue`);
  }

  /** Manage doctors (receptionist) */
  manageDoctors(options: {
    hospitalId?: string; department?: string;
    search?: string; page?: number; pageSize?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.hospitalId) params = params.set('hospital_id', options.hospitalId);
    if (options.department) params = params.set('department', options.department);
    if (options.search) params = params.set('search', options.search);
    if (options.page) params = params.set('page', options.page.toString());
    if (options.pageSize) params = params.set('page_size', options.pageSize.toString());
    return this.http.get(`${this.ADMIN_API}/manage`, { params });
  }

  // ── DEPARTMENT METHODS ──

  /** List departments — hits /list endpoint which returns { success, data: [...] } */
  listDepartments(hospitalId?: string): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.DEPARTMENT_LIST_API}`, { params });
  }

  /** List departments for admin management — same /list endpoint */
  listAdminDepartments(hospitalId?: string): Observable<any> {
    let params = new HttpParams();
    if (hospitalId) params = params.set('hospital_id', hospitalId);
    return this.http.get(`${this.DEPARTMENT_LIST_API}`, { params });
  }

  /** Create a new department (Admin only) */
  createDepartment(payload: { name: string; description: string; hospital_id: string }): Observable<any> {
    return this.http.post(`${this.DEPARTMENT_API}`, payload);
  }

  /** Update a department (Admin only) */
  updateDepartment(id: string, payload: { name: string; description: string }): Observable<any> {
    return this.http.patch(`${this.DEPARTMENT_API}/${id}`, payload);
  }

  /** Delete a department (Admin only) */
  deleteDepartment(id: string): Observable<any> {
    return this.http.delete(`${this.DEPARTMENT_API}/${id}`);
  }

  // ============================================================
  // Legacy compatibility methods (for existing components)
  // These use the BehaviorSubject for components that still
  // work with the old Doctor[] interface.
  // ============================================================

  /** Convert API response to legacy Doctor model */
  private toLegacyDoctor(apiDoc: DoctorApiResponse): Doctor {
    return {
      id: apiDoc.id,
      name: apiDoc.name,
      specialization: apiDoc.department,
      qualifications: '',
      timings: `${apiDoc.start_time} – ${apiDoc.end_time}`,
      available: apiDoc.status === 'available',
      fee: `Rs. ${apiDoc.consultation_fee}`,
      department: apiDoc.department,
      onLeave: apiDoc.status === 'on_leave'
    };
  }

  /** Legacy: get doctors array synchronously from cache */
  getDoctors(): Doctor[] {
    return this.doctorsSubject.value;
  }

  /** Legacy: observable of doctors */
  getDoctorsObservable(): Observable<Doctor[]> {
    return this.doctors$;
  }

  /** Legacy: update doctor in local cache */
  updateDoctor(updatedDoctor: Doctor): void {
    const current = this.doctorsSubject.value;
    const index = current.findIndex(d => d.id === updatedDoctor.id);
    if (index !== -1) {
      current[index] = updatedDoctor;
      this.doctorsSubject.next([...current]);
    }
  }

  /** Legacy: add doctor to local cache */
  addDoctor(doctor: Omit<Doctor, 'id'>): void {
    const maxId = Math.max(...this.doctorsSubject.value.map(d => parseInt(d.id)), 0);
    const newId = (maxId + 1).toString();
    const newDoctor: Doctor = { ...doctor, id: newId };
    this.doctorsSubject.next([...this.doctorsSubject.value, newDoctor]);
  }

  /** Legacy: delete doctor from local cache */
  deleteDoctor(id: string): void {
    const filtered = this.doctorsSubject.value.filter(d => d.id !== id);
    this.doctorsSubject.next(filtered);
  }

  /** Load doctors from API and populate the legacy BehaviorSubject */
  loadDoctorsFromApi(hospitalId?: string): void {
    this.listDoctors({ hospitalId, limit: 100 }).pipe(
      map((response: any) => {
        const docs = response?.doctors || response || [];
        return Array.isArray(docs) ? docs.map((d: any) => this.toLegacyDoctor(d)) : [];
      }),
      catchError(() => of([]))
    ).subscribe(doctors => {
      this.doctorsSubject.next(doctors);
    });
  }
}