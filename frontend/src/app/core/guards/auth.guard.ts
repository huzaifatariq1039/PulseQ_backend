import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { AuthService } from '../services/auth.service';
import { detectPortal } from '../config/portal-detector';

function getAuthPageForUrl(url: string): string {
    const cleanUrl = url.split('?')[0].split('#')[0];

    if (cleanUrl.startsWith('/patient')) return '/patient/auth';
    if (cleanUrl.startsWith('/staff/doctor')) return '/staff/doctor/auth';
    if (cleanUrl.startsWith('/staff/reception')) return '/staff/reception/auth';
    if (cleanUrl.startsWith('/staff/pharmacy')) return '/staff/pharmacy/auth';
    if (cleanUrl.startsWith('/staff/admin')) return '/staff/admin/auth';

    // Root-level single-portal deployment — auth is always at /auth
    return '/auth';
}

export const authGuard: CanActivateFn = (route, state) => {
    const router = inject(Router);
    const authService = inject(AuthService);
    const platformId = inject(PLATFORM_ID);
    const isBrowser = isPlatformBrowser(platformId);

    if (isBrowser) {
        const token = localStorage.getItem('pulseq_token');
        const user = localStorage.getItem('pulseq_user');

        if (token && user) {
            try {
                JSON.parse(user);
                return true;
            } catch {
                authService.logout();
                return router.parseUrl(getAuthPageForUrl(state.url));
            }
        }

        return router.parseUrl(getAuthPageForUrl(state.url));
    }

    return router.parseUrl('/auth');
};