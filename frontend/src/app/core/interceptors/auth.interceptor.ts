import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const platformId = inject(PLATFORM_ID);
  const isBrowser = isPlatformBrowser(platformId);

  const router = inject(Router);

  let apiReq = req;

  // rewrite relative /api URLs to the absolute backend URL
  if (!isBrowser && req.url.startsWith('/api')) {
    const absoluteUrl = `${environment.apiBaseUrl}${req.url.replace('/api/v1', '')}`;
    apiReq = req.clone({ url: absoluteUrl });
  }

  // Only attach token to our own API calls
  const isApiRequest = apiReq.url.startsWith('/api') ||
    apiReq.url.includes(environment.apiBaseUrl.replace('/api/v1', ''));

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
    return next(cloned).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          if (isBrowser) {
            try {
              localStorage.removeItem('pulseq_token');
              localStorage.removeItem('pulseq_user');
              localStorage.removeItem('hospitalId');
              localStorage.removeItem('doctorId');
            } catch (e) {
              console.error('Failed to clear localStorage:', e);
            }
          }
          const currentUrl = isBrowser ? window.location.pathname : '';
          let redirectPath = '/auth';
          if (currentUrl.includes('/patient')) {
            redirectPath = '/patient/auth';
          } else if (currentUrl.includes('/doctor')) {
            redirectPath = '/doctor/auth';
          } else if (currentUrl.includes('/admin')) {
            redirectPath = '/admin/auth';
          } else if (currentUrl.includes('/reception')) {
            redirectPath = '/reception/auth';
          } else if (currentUrl.includes('/pharmacy')) {
            redirectPath = '/pharmacy/auth';
          }
          router.navigate([redirectPath]).catch(err => {
            console.error(`Navigation to ${redirectPath} failed:`, err);
          });
          console.warn(`401 Unauthorized - Redirecting to ${redirectPath}`, error);
        }
        return throwError(() => error);
      })
    );
  }

  return next(apiReq);
};
