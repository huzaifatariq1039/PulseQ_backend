import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { environment } from '../../../environments/environment';

export const authGuard: CanActivateFn = (route, state) => {
    const router = inject(Router);
    const platformId = inject(PLATFORM_ID);
    const isBrowser = isPlatformBrowser(platformId);

    if (isBrowser) {
        const token = localStorage.getItem('pulseq_token');
        if (token) {
            return true;
        }
        const portalAuthMap: Record<string, string> = {
            pharmacy: '/staff/pharmacy/auth',     // pharmacy portal root auth
            patient: '/patient/auth',
            doctor: '/doctor/auth',
            admin: '/admin/auth',
            reception: '/reception/auth',
        };

        const redirectUrl = portalAuthMap[environment.portal] ?? '/auth';
        return router.parseUrl(redirectUrl);
    }

    return false;
};