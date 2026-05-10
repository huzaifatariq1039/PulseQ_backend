import { environment } from '../../../environments/environment';

export function pharmacyPath(path: string): string {
  const isLocalhost = typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
     window.location.hostname === '127.0.0.1');
  const base = isLocalhost ? '/staff/pharmacy' : '';
  return `${base}/${path}`;
}