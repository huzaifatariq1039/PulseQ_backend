import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * OTP Testing Service
 * 
 * This service provides utilities for testing and debugging OTP functionality
 * during development. It should be used only in development environment.
 * 
 * Features:
 * - Get the OTP sent to a phone number (for testing)
 * - Verify OTP status
 * - Clear OTP attempts
 * - Get OTP expiry information
 */

export interface OtpTestResponse {
    status: string;
    message: string;
    otp?: string;
    expiresIn?: number;
    attempts?: number;
    phone?: string;
}

export interface OtpStatusResponse {
    phone: string;
    status: 'pending' | 'verified' | 'expired';
    attemptCount: number;
    remainingAttempts: number;
    expiresAt: string;
}

@Injectable({
    providedIn: 'root'
})
export class OtpTestingService {
    private readonly API = environment.apiBaseUrl;
    private isDevelopment = !environment.production;

    constructor(private http: HttpClient) {
        if (this.isDevelopment) {
            console.log('[OTP Testing Service] Initialized in DEVELOPMENT mode');
        }
    }

    /**
     * Get the OTP for testing purposes (DEVELOPMENT ONLY)
     * This endpoint should only be available in development
     */
    getOtpForTesting(phone: string): Observable<OtpTestResponse> {
        if (!this.isDevelopment) {
            console.warn('[OTP Testing Service] Cannot access testing OTP in production');
            throw new Error('OTP testing is not available in production');
        }
        return this.http.get<OtpTestResponse>(
            `${this.API}/auth/test/phone-otp/${phone}`
        );
    }

    /**
     * Get OTP status for a phone number (DEVELOPMENT ONLY)
     */
    getOtpStatus(phone: string): Observable<OtpStatusResponse> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.get<OtpStatusResponse>(
            `${this.API}/auth/test/phone-otp-status/${phone}`
        );
    }

    /**
     * Clear OTP attempts for a phone number (DEVELOPMENT ONLY)
     */
    clearOtpAttempts(phone: string): Observable<any> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.post(
            `${this.API}/auth/test/clear-phone-otp`,
            { phone }
        );
    }

    /**
     * Get forgotten password OTP (DEVELOPMENT ONLY)
     */
    getForgotPasswordOtp(email: string): Observable<OtpTestResponse> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.get<OtpTestResponse>(
            `${this.API}/auth/test/forgot-password-otp/${email}`
        );
    }

    /**
     * Get OTP info for email (DEVELOPMENT ONLY)
     */
    getForgotPasswordOtpStatus(email: string): Observable<OtpStatusResponse> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.get<OtpStatusResponse>(
            `${this.API}/auth/test/forgot-password-otp-status/${email}`
        );
    }

    /**
     * Check SMS delivery status (DEVELOPMENT ONLY)
     */
    checkSmsDeliveryStatus(phone: string): Observable<any> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.get(
            `${this.API}/auth/test/sms-delivery-status/${phone}`
        );
    }

    /**
     * Simulate SMS delivery delay/failure (DEVELOPMENT ONLY)
     */
    simulateSmsDelivery(phone: string, status: 'success' | 'failure' | 'delay'): Observable<any> {
        if (!this.isDevelopment) {
            throw new Error('OTP testing is not available in production');
        }
        return this.http.post(
            `${this.API}/auth/test/simulate-sms`,
            { phone, status }
        );
    }

    /**
     * Log current OTP state for debugging
     */
    logOtpState(phone: string, context?: string): void {
        if (this.isDevelopment) {
            console.group('[OTP Testing] State Debug', context || '');
            this.getOtpStatus(phone).subscribe({
                next: (status) => {
                    console.table({
                        'Phone': status.phone,
                        'Status': status.status,
                        'Attempts': status.attemptCount,
                        'Remaining': status.remainingAttempts,
                        'Expires At': status.expiresAt
                    });
                    console.groupEnd();
                },
                error: (err) => {
                    console.error('[OTP Testing] Failed to get status:', err);
                    console.groupEnd();
                }
            });
        }
    }
}
