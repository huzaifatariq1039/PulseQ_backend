import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import { map, tap, catchError, switchMap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface AuthUser {
  id?: string;
  email: string;
  name?: string;
  phone?: string;
  role?: string;
  hospitalId?: string;
  location_access?: boolean;
  created_at?: string;
}

export interface LoginRequest {
  identifier: string;
  password: string;
  auth_method?: 'phone' | 'email';
  location_access?: boolean;
}

export interface RegisterRequest {
  name: string;
  email?: string;
  phone?: string;
  password: string;
  auth_method?: 'phone' | 'email';
}

export interface PharmacyLoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly API = environment.apiBaseUrl;

  private userSubject = new BehaviorSubject<AuthUser | null>(null);
  user$ = this.userSubject.asObservable();

  constructor(private http: HttpClient) {
    try {
      const raw = typeof window !== 'undefined' ? localStorage.getItem('pulseq_user') : null;
      if (raw) {
        this.userSubject.next(JSON.parse(raw));
      }
    } catch { }
  }

  login(
    identifier: string,
    password: string,
    authMethod: 'phone' | 'email' = 'email',
    portal: 'patient' | 'receptionist' | 'admin' | 'doctor' | null = null
  ): Observable<boolean> {
    const body: LoginRequest = {
      identifier,
      password,
      auth_method: authMethod,
      location_access: false
    };

    const endpoint = portal
      ? `${this.API}/auth/${portal}/login`
      : `${this.API}/auth/login`;

    return this.http.post<TokenResponse>(endpoint, body).pipe(
      tap(response => {
        this.storeToken(response.access_token);
      }),
      switchMap(() =>
        this.fetchCurrentUser().pipe(
          map(() => true),
          catchError(() => of(true))
        )
      ),
      catchError(err => {
        console.error('[AuthService] Login failed:', err);
        return of(false);
      })
    );
  }

  pharmacyLogin(email: string, password: string): Observable<boolean> {
    const body: PharmacyLoginRequest = { email, password };

    return this.http.post<TokenResponse>(`${this.API}/auth/pharmacy/login`, body).pipe(
      tap(response => {
        this.storeToken(response.access_token);
      }),
      switchMap(() =>
        this.fetchCurrentUser().pipe(
          map(() => true),
          catchError(() => of(true))
        )
      ),
      catchError(err => {
        console.error('[AuthService] Pharmacy login failed:', err);
        return of(false);
      })
    );
  }

  register(data: RegisterRequest): Observable<AuthUser> {
    return this.http.post<AuthUser>(`${this.API}/auth/register`, data).pipe(
      tap(user => {
        console.log('[AuthService] Registration successful:', user);
      }),
      catchError(err => {
        console.error('[AuthService] Registration failed:', err);
        return throwError(() => err);
      })
    );
  }

  // ─── Forgot Password Flow (phone-based) ───────────────────────────────────

  /**
   * Step 1: Send OTP to phone number
   * Backend expects: { phone: "1234567890" }
   */
  forgotPassword(phone: string): Observable<any> {
    return this.http.post(`${this.API}/auth/forgot-password`, { phone }).pipe(
      catchError(err => {
        console.error('[AuthService] Forgot password failed:', err);
        return throwError(() => err);
      })
    );
  }

  /**
   * Step 2: Verify OTP sent to phone
   * Backend expects: { phone: "1234567890", otp: "123456" }
   */
  verifyOtp(phone: string, otp: string): Observable<any> {
    return this.http.post(`${this.API}/auth/verify-otp`, { phone, otp }).pipe(
      catchError(err => {
        console.error('[AuthService] OTP verification failed:', err);
        return throwError(() => err);
      })
    );
  }

  /**
   * Step 3: Reset password using phone + otp
   * Backend expects: { phone: "1234567890", otp: "123456", new_password: "..." }
   */
  resetPasswordWithOtp(phone: string, otp: string, newPassword: string): Observable<any> {
    return this.http.post(`${this.API}/auth/reset-password`, {
      phone,
      otp,
      new_password: newPassword
    }).pipe(
      catchError(err => {
        console.error('[AuthService] Reset password with OTP failed:', err);
        return throwError(() => err);
      })
    );
  }

  /**
   * Resend OTP to phone number
   * Backend expects: { phone: "1234567890" }
   */
  resendOtp(phone: string): Observable<any> {
    return this.http.post(`${this.API}/auth/resend-otp`, { phone }).pipe(
      catchError(err => {
        console.error('[AuthService] Resend OTP failed:', err);
        return throwError(() => err);
      })
    );
  }

  // ─── Phone Verification During Registration ───────────────────────────────

  sendPhoneVerificationOtp(phone: string): Observable<any> {
    return this.http.post(`${this.API}/auth/send-phone-otp`, { phone }).pipe(
      catchError(err => {
        console.error('[AuthService] Send phone verification OTP failed:', err);
        return throwError(() => err);
      })
    );
  }

  verifyPhoneOtp(phone: string, otp: string): Observable<any> {
    return this.http.post(`${this.API}/auth/verify-phone-otp`, { phone, otp }).pipe(
      catchError(err => {
        console.error('[AuthService] Verify phone OTP failed:', err);
        return throwError(() => err);
      })
    );
  }

  resendPhoneVerificationOtp(phone: string): Observable<any> {
    return this.http.post(`${this.API}/auth/resend-phone-otp`, { phone }).pipe(
      catchError(err => {
        console.error('[AuthService] Resend phone OTP failed:', err);
        return throwError(() => err);
      })
    );
  }

  // ─── Phone Number Management ──────────────────────────────────────────────

  updatePhoneNumber(newPhone: string, otp?: string): Observable<any> {
    const body = otp ? { phone: newPhone, otp } : { phone: newPhone };
    return this.http.post(`${this.API}/auth/update-phone`, body).pipe(
      catchError(err => {
        console.error('[AuthService] Update phone number failed:', err);
        return throwError(() => err);
      })
    );
  }

  // ─── Misc ─────────────────────────────────────────────────────────────────

  resetPassword(token: string, newPassword: string): Observable<any> {
    return this.http.post(`${this.API}/auth/reset-password`, {
      token,
      new_password: newPassword
    }).pipe(
      catchError(err => {
        console.error('[AuthService] Reset password failed:', err);
        return throwError(() => err);
      })
    );
  }

  checkPhoneExists(phone: string): Observable<any> {
    return this.http.get(`${this.API}/auth/check-phone/${phone}`);
  }

  checkAvailability(params: { email?: string; phone?: string }): Observable<any> {
    return this.http.get(`${this.API}/auth/check-availability`, { params: params as any });
  }

  fetchCurrentUser(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${this.API}/auth/me`).pipe(
      tap(user => {
        this.userSubject.next(user);
        try {
          localStorage.setItem('pulseq_user', JSON.stringify(user));
        } catch { }
      })
    );
  }

  getLocationAccess(): Observable<any> {
    return this.http.get(`${this.API}/auth/location-access`);
  }

  updateLocationAccess(locationAccess: boolean): Observable<any> {
    return this.http.post(`${this.API}/auth/location-access`, { location_access: locationAccess });
  }

  logout(): void {
    this.userSubject.next(null);
    try {
      localStorage.removeItem('pulseq_user');
      localStorage.removeItem('pulseq_token');
    } catch { }
  }

  getToken(): string | null {
    try {
      return typeof window !== 'undefined' ? localStorage.getItem('pulseq_token') : null;
    } catch {
      return null;
    }
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  getCurrentUser(): AuthUser | null {
    return this.userSubject.value;
  }

  private storeToken(token: string): void {
    try {
      localStorage.setItem('pulseq_token', token);
    } catch { }
  }
}