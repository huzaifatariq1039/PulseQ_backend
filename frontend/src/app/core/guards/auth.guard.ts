import { inject } from '@angular/core';
import { CanActivateFn } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export const authGuard: CanActivateFn = (route, state) => {
    const platformId = inject(PLATFORM_ID);
    const isBrowser = isPlatformBrowser(platformId);
    let token: string | null = null;
    if (isBrowser) {
        token = localStorage.getItem('pulseq_token');
        if (token) {
            return true;
        } else {
            // With per-portal subdomain builds, auth is always at /auth
            window.location.href = '/auth';
            return false;
        }
    }
    // On server, always deny navigation
    return false;
};
