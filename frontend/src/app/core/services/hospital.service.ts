import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface HospitalResponse {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  phone: string;
  email?: string;
  rating?: number;
  review_count?: number;
  status?: 'open' | 'closed' | 'maintenance';
  specializations?: string[];
  latitude?: number;
  longitude?: number;
  distance_km?: number;
  estimated_time_minutes?: number;
  created_at?: string;
  updated_at?: string;
  is_open?: boolean;
  is_database?: boolean;
  source?: string;
  availableDoctors?: number;
  has_doctors?: boolean;
  is_nearby?: boolean;
}

export interface HospitalSearchResponse {
  hospitals: HospitalResponse[];
  total_found: number;
  search_query?: string;
}

export interface HospitalLite {
  id: string;
  name: string;
  address?: string;
  city?: string;
  state?: string;
  latitude?: number;
  longitude?: number;
  distance_km?: number;
  estimated_time_minutes?: number;
  rating?: number;
  review_count?: number;
  status?: string;
  source?: string;
  is_nearby?: boolean;
  is_database?: boolean;
}

export interface HospitalUnifiedSearchResponse {
  hospitals: HospitalLite[];
  total_found: number;
  search_query?: string;
}

export interface HospitalCreate {
  name: string;
  address: string;
  city: string;
  state: string;
  phone: string;
  email?: string;
  rating?: number;
  status?: 'open' | 'closed' | 'maintenance';
  specializations?: string[];
  latitude?: number;
  longitude?: number;
}

@Injectable({
  providedIn: 'root'
})
export class HospitalService {
  private readonly API = `${environment.apiBaseUrl}/public/hospitals`;

  constructor(private http: HttpClient) { }

  /** List all hospitals with pagination */
  listHospitals(limit = 20, page = 1): Observable<any> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('page', page.toString());
    return this.http.get(this.API, { params });
  }

  /** Get hospital by ID */
  getHospital(hospitalId: string): Observable<HospitalResponse> {
    return this.http.get<HospitalResponse>(`${this.API}/${hospitalId}`);
  }

  /** Create a new hospital (Admin only) */
  createHospital(data: HospitalCreate): Observable<HospitalResponse> {
    return this.http.post<HospitalResponse>(this.API, data);
  }

  /** Update hospital details (Admin only) */
  updateHospital(hospitalId: string, data: any): Observable<any> {
    return this.http.put(`${this.API}/${hospitalId}`, data);
  }

  /** Delete hospital (Admin only) */
  deleteHospital(hospitalId: string): Observable<any> {
    return this.http.delete(`${this.API}/${hospitalId}`);
  }

  /** Search hospitals by name, specialization, or city */
  searchHospitals(query: string, city?: string, limit = 10, userLat?: number, userLng?: number): Observable<HospitalSearchResponse> {
    let params = new HttpParams().set('query', query).set('limit', limit.toString());
    if (city) params = params.set('city', city);
    if (userLat !== undefined) params = params.set('user_lat', userLat.toString());
    if (userLng !== undefined) params = params.set('user_lng', userLng.toString());
    return this.http.get<HospitalSearchResponse>(`${this.API}/search`, { params });
  }

  /** Unified search: merged list of DB + OSM hospitals */
  searchHospitalsUnified(options: {
    query?: string; city?: string; limit?: number;
    userLat?: number; userLng?: number; radiusKm?: number;
    includeDb?: boolean; includeOsm?: boolean;
  } = {}): Observable<HospitalUnifiedSearchResponse> {
    let params = new HttpParams();
    if (options.query) params = params.set('query', options.query);
    if (options.city) params = params.set('city', options.city);
    if (options.limit) params = params.set('limit', options.limit.toString());
    if (options.userLat !== undefined) params = params.set('user_lat', options.userLat.toString());
    if (options.userLng !== undefined) params = params.set('user_lng', options.userLng.toString());
    if (options.radiusKm !== undefined) params = params.set('radius_km', options.radiusKm.toString());
    if (options.includeDb !== undefined) params = params.set('include_db', options.includeDb.toString());
    if (options.includeOsm !== undefined) params = params.set('include_osm', options.includeOsm.toString());
    return this.http.get<HospitalUnifiedSearchResponse>(`${this.API}/search-unified`, { params });
  }

  /** Get nearby hospitals from DB */
  getNearbyHospitals(options: {
    city?: string; userLat?: number; userLng?: number;
    radiusKm?: number; limit?: number;
  } = {}): Observable<HospitalSearchResponse> {
    let params = new HttpParams();
    if (options.city) params = params.set('city', options.city);
    if (options.userLat !== undefined) params = params.set('user_lat', options.userLat.toString());
    if (options.userLng !== undefined) params = params.set('user_lng', options.userLng.toString());
    if (options.radiusKm !== undefined) params = params.set('radius_km', options.radiusKm.toString());
    if (options.limit) params = params.set('limit', options.limit.toString());
    return this.http.get<HospitalSearchResponse>(`${this.API}/nearby`, { params });
  }

  /** Get nearby hospitals from OpenStreetMap (Overpass API) */
  getNearbyHospitalsOverpass(lat: number, lng: number, radiusM = 5000, limit = 20): Observable<any> {
    const params = new HttpParams()
      .set('lat', lat.toString())
      .set('lng', lng.toString())
      .set('radius_m', radiusM.toString())
      .set('limit', limit.toString());
    return this.http.get(`${this.API}/nearby-overpass`, { params });
  }

  /** Get nearby hospitals from OpenStreetMap (Nominatim API) */
  getNearbyHospitalsOsm(lat: number, lng: number, radiusM = 2000, limit = 10): Observable<any> {
    const params = new HttpParams()
      .set('lat', lat.toString())
      .set('lng', lng.toString())
      .set('radius_m', radiusM.toString())
      .set('limit', limit.toString());
    return this.http.get(`${this.API}/nearby-osm`, { params });
  }

  /** Get hospitals by radius */
  getHospitalsByRadius(lat: number, lng: number, radiusKm = 25, limit = 20): Observable<HospitalSearchResponse> {
    const params = new HttpParams()
      .set('lat', lat.toString())
      .set('lng', lng.toString())
      .set('radius_km', radiusKm.toString())
      .set('limit', limit.toString());
    return this.http.get<HospitalSearchResponse>(`${this.API}/nearby-radius`, { params });
  }

  /** Get OPEN hospitals from SmartToken database */
  getOpenHospitals(city?: string, limit = 50): Observable<HospitalSearchResponse> {
    let params = new HttpParams().set('limit', limit.toString());
    if (city) params = params.set('city', city);
    return this.http.get<HospitalSearchResponse>(`${this.API}/open`, { params });
  }

  /** Get nearby hospitals with doctors */
  getNearbyHospitalsWithDoctors(options: {
    city?: string; userLat?: number; userLng?: number;
    mainCategory?: string; subcategory?: string;
    perHospitalLimit?: number; hospitalsLimit?: number; radiusKm?: number;
  } = {}): Observable<any> {
    let params = new HttpParams();
    if (options.city) params = params.set('city', options.city);
    if (options.userLat !== undefined) params = params.set('user_lat', options.userLat.toString());
    if (options.userLng !== undefined) params = params.set('user_lng', options.userLng.toString());
    if (options.mainCategory) params = params.set('main_category', options.mainCategory);
    if (options.subcategory) params = params.set('subcategory', options.subcategory);
    if (options.perHospitalLimit) params = params.set('per_hospital_limit', options.perHospitalLimit.toString());
    if (options.hospitalsLimit) params = params.set('hospitals_limit', options.hospitalsLimit.toString());
    if (options.radiusKm) params = params.set('radius_km', options.radiusKm.toString());
    return this.http.get(`${this.API}/nearby-with-doctors`, { params });
  }

  /** Get hospital doctors */
  getHospitalDoctors(hospitalId: string, category?: string): Observable<any> {
    let params = new HttpParams();
    if (category) params = params.set('category', category);
    return this.http.get(`${this.API}/${hospitalId}/doctors`, { params });
  }

  /** Get hospital doctors by main category */
  getHospitalDoctorsByMainCategory(hospitalId: string, mainCategory: string, limit = 50): Observable<any> {
    const params = new HttpParams()
      .set('main_category', mainCategory)
      .set('limit', limit.toString());
    return this.http.get(`${this.API}/${hospitalId}/doctors/by-category`, { params });
  }

  /** Get hospital doctors by subcategory */
  getHospitalDoctorsBySubcategory(hospitalId: string, subcategory: string, limit = 50): Observable<any> {
    const params = new HttpParams()
      .set('subcategory', subcategory)
      .set('limit', limit.toString());
    return this.http.get(`${this.API}/${hospitalId}/doctors/by-subcategory`, { params });
  }

  /** Get activated departments for a hospital */
  getHospitalDepartments(hospitalId: string): Observable<any> {
    return this.http.get(`${environment.apiBaseUrl}/staff/doctors/departments`, {
      params: new HttpParams().set('hospital_id', hospitalId)
    });
  }
}