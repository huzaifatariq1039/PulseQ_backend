import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export const authGuard: CanActivateFn = (route, state) => {
    const router = inject(Router);
    const platformId = inject(PLATFORM_ID);
    const isBrowser = isPlatformBrowser(platformId);
    let token: string | null = null;
    if (isBrowser) {
        token = localStorage.getItem('pulseq_token');
        if (token) {
            return true;
        } else {
            const targetUrl = state.url.startsWith('/patient') ? '/patient/auth' : '/auth';
            return router.parseUrl(targetUrl);
        }
    }
    // On server, always deny navigation
    return false;
};
