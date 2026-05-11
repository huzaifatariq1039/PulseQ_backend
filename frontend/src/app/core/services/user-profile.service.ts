import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface UserProfile {
  fullName: string;
  email: string;
  profilePicture: string | null;
  initials: string;
  // API fields
  id?: string;
  phone?: string;
  role?: string;
  location_access?: boolean;
  created_at?: string;
}

export interface ProfileUpdate {
  name?: string;
  email?: string;
  phone?: string;
  location_access?: boolean;
}

export interface AppointmentHistory {
  id: string;
  doctor_name: string;
  doctor_specialization: string;
  hospital_name: string;
  appointment_date: string;
  status: string;
  rating?: number;
  token_number: string;
}

@Injectable({
  providedIn: 'root'
})
export class UserProfileService {
  private readonly API = `${environment.apiBaseUrl}/patient/profile`;

  private profileSubject = new BehaviorSubject<UserProfile | null>(null);
  public profile$ = this.profileSubject.asObservable();

  constructor(private http: HttpClient) {
    this.loadProfile();
  }

  // ============================================================
  //  Backend API methods
  // ============================================================

  /** Get user profile from API */
  fetchProfile(): Observable<any> {
    return this.http.get(`${this.API}/`).pipe(
      tap((apiUser: any) => {
        const profile = this.apiToProfile(apiUser);
        this.profileSubject.next(profile);
        this.saveProfileLocal(profile);
      }),
      catchError(err => {
        console.error('[UserProfileService] Failed to fetch profile:', err);
        return of(null);
      })
    );
  }

  /** Update user profile via API (PUT) */
  updateProfileApi(data: ProfileUpdate): Observable<any> {
    return this.http.put(`${this.API}/`, data).pipe(
      tap((apiUser: any) => {
        const profile = this.apiToProfile(apiUser);
        this.profileSubject.next(profile);
        this.saveProfileLocal(profile);
      })
    );
  }

  /** Update user profile via API (PATCH) */
  patchProfileApi(data: ProfileUpdate): Observable<any> {
    return this.http.patch(`${this.API}/`, data).pipe(
      tap((apiUser: any) => {
        const profile = this.apiToProfile(apiUser);
        this.profileSubject.next(profile);
        this.saveProfileLocal(profile);
      })
    );
  }

  /** Upload avatar as file */
  uploadAvatarFile(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.API}/avatar/upload-file`, formData);
  }

  /** Upload avatar as base64 */
  uploadAvatarBase64(payload: { image: string; content_type?: string }): Observable<any> {
    return this.http.post(`${this.API}/avatar/upload-base64`, payload);
  }

  /** Get avatar image */
  getAvatar(): Observable<any> {
    return this.http.get(`${this.API}/avatar`);
  }

  /** Delete avatar */
  deleteAvatar(): Observable<any> {
    return this.http.delete(`${this.API}/avatar`);
  }

  /** Get appointment history */
  getAppointmentHistory(): Observable<AppointmentHistory[]> {
    return this.http.get<AppointmentHistory[]>(`${this.API}/appointment-history`);
  }

  /** Change password */
  changePassword(currentPassword: string, newPassword: string): Observable<any> {
    const params = { current_password: currentPassword, new_password: newPassword };
    return this.http.post(`${this.API}/change-password`, null, { params });
  }

  /** Delete account */
  deleteAccount(): Observable<any> {
    return this.http.delete(`${this.API}/account`);
  }

  /** Get profile statistics */
  getProfileStatistics(): Observable<any> {
    return this.http.get(`${this.API}/statistics`);
  }

  // ============================================================
  //  Legacy local methods (backward compatibility)
  // ============================================================

  private loadProfile(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const storedProfile = window.localStorage.getItem('userProfile');
        if (storedProfile) {
          const profile = JSON.parse(storedProfile);
          this.profileSubject.next(profile);
          return;
        }
        const userRaw = window.localStorage.getItem('pulseq_user');
        if (userRaw) {
          const user = JSON.parse(userRaw);
          const profile = this.apiToProfile(user);
          this.profileSubject.next(profile);
          window.localStorage.setItem('userProfile', JSON.stringify(profile));
          return;
        }
        this.profileSubject.next(null);
      }
    } catch { /* ignore */ }
  }

  private apiToProfile(apiUser: any): UserProfile {
    const name = apiUser?.name || apiUser?.fullName || '';
    const nameParts = name.split(' ');
    return {
      fullName: name,
      email: apiUser?.email || '',
      profilePicture: apiUser?.profilePicture || apiUser?.avatar_url || null,
      initials: nameParts.map((n: string) => n[0]).join('').toUpperCase() || '?',
      id: apiUser?.id,
      phone: apiUser?.phone,
      role: apiUser?.role,
      location_access: apiUser?.location_access,
      created_at: apiUser?.created_at
    };
  }

  getProfile(): UserProfile | null {
    return this.profileSubject.getValue();
  }

  saveProfile(profile: UserProfile): void {
    this.profileSubject.next(profile);
    this.saveProfileLocal(profile);
  }

  private saveProfileLocal(profile: UserProfile): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem('userProfile', JSON.stringify(profile));
      }
    } catch { /* ignore */ }
  }

  updateProfilePicture(picture: string | null): void {
    const currentProfile = this.profileSubject.getValue();
    if (!currentProfile) return;
    const updatedProfile: UserProfile = { ...currentProfile, profilePicture: picture };
    this.saveProfile(updatedProfile);
  }

  updateFullName(fullName: string): void {
    const names = fullName.split(' ');
    const initials = `${names[0]?.charAt(0) || ''}${names[1]?.charAt(0) || ''}`.toUpperCase();
    const currentProfile = this.profileSubject.getValue();
    if (!currentProfile) return;
    const updatedProfile: UserProfile = { ...currentProfile, fullName, initials };
    this.saveProfile(updatedProfile);
  }

  updateEmail(email: string): void {
    const currentProfile = this.profileSubject.getValue();
    if (!currentProfile) return;
    const updatedProfile: UserProfile = { ...currentProfile, email };
    this.saveProfile(updatedProfile);
  }
}
