import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { AuthService } from '../services/auth.service';

/**
 * Helper function to determine the correct auth page based on the current URL
 */
function getAuthPageForUrl(url: string): string {
    // Strip query params and fragments
    const cleanUrl = url.split('?')[0].split('#')[0];

    // Check portal prefixes in order
    if (cleanUrl.startsWith('/patient')) {
        return '/patient/auth';
    } else if (cleanUrl.startsWith('/staff/doctor')) {
        return '/staff/doctor/auth';
    } else if (cleanUrl.startsWith('/staff/reception')) {
        return '/staff/reception/auth';
    } else if (cleanUrl.startsWith('/staff/pharmacy')) {
        return '/staff/pharmacy/auth';
    } else if (cleanUrl.startsWith('/staff/admin')) {
        return '/staff/admin/auth';
    }

    // Fallback to patient auth (most common)
    return '/patient/auth';
}

export const authGuard: CanActivateFn = (route, state) => {
    const router = inject(Router);
    const authService = inject(AuthService);
    const platformId = inject(PLATFORM_ID);
    const isBrowser = isPlatformBrowser(platformId);

    if (isBrowser) {
        const token = localStorage.getItem('pulseq_token');
        const user = localStorage.getItem('pulseq_user');

        // Token exists and user data exists
        if (token && user) {
            try {
                // Validate user data is valid JSON
                JSON.parse(user);
                return true;
            } catch {
                // Corrupted user data - clear and redirect to correct auth page
                authService.logout();
                const authPage = getAuthPageForUrl(state.url);
                return router.parseUrl(authPage);
            }
        }

        // No token or user data found - redirect to appropriate auth page
        if (!token || !user) {
            const authPage = getAuthPageForUrl(state.url);
            return router.parseUrl(authPage);
        }
    }

    // On server, redirect to patient auth to prevent prerendering protected content
    return router.parseUrl('/patient/auth');
};
