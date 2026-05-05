import { HttpInterceptorFn } from '@angular/common/http';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const platformId = inject(PLATFORM_ID);
  const isBrowser = isPlatformBrowser(platformId);

  let apiReq = req;

  // rewrite relative /api URLs to the absolute backend URL
  if (!isBrowser && req.url.startsWith('/api')) {
    const absoluteUrl = `https://oyster-app-notep.ondigitalocean.app${req.url}`;
    apiReq = req.clone({ url: absoluteUrl });
  }

  // Only attach token to our own API calls
  const isApiRequest = apiReq.url.startsWith('/api') ||
    apiReq.url.includes('oyster-app-notep.ondigitalocean.app');

  if (!isApiRequest) {
    return next(apiReq);
  }

  let token: string | null = null;
  try {
    if (isBrowser) {
      token = localStorage.getItem('pulseq_token');
    }
  } catch { /* SSR-safe */ }

  if (token) {
    const cloned = apiReq.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
    return next(cloned);
  }

  return next(apiReq);
};
