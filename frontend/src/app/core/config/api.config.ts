/**
 * Centralized API configuration utility.
 * 
 * Supports both client-side (via import.meta.env.VITE_*) and SSR (via process.env).
 * Falls back to sensible defaults if environment variables are not set.
 */

import { environment } from '../../../environments/environment';

const DEFAULT_SSR_DEV_URL = 'http://localhost:4000';

export const API_BASE_URL = environment.apiBaseUrl;

/**
 * Get the SSR base URL for server-side requests.
 * Uses SSR_BASE_URL or VITE_SSR_URL environment variable, defaults to localhost:4000
 */
export function getSsrBaseUrl(): string {
  // Try SSR_BASE_URL (process.env)
  if (typeof process !== 'undefined' && process.env && process.env['SSR_BASE_URL']) {
    return process.env['SSR_BASE_URL'];
  }

  // Try VITE_SSR_URL for consistency
  try {
    // For Vite builds, import.meta.env is available
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const env = (import.meta as any)?.env?.VITE_SSR_URL;
    if (env) {
      return env;
    }
  } catch {
    // Silent fallback for non-module environments
  }

  // Fallback to default
  return DEFAULT_SSR_DEV_URL;
}

/**
 * Detect if we're in a development environment (localhost).
 * Checks window.location.hostname or process.env
 */
export function isDevelopmentEnvironment(): boolean {
  // Server-side check
  if (typeof window === 'undefined' && typeof process !== 'undefined') {
    const url = process.env?.['SSR_BASE_URL'] || DEFAULT_SSR_DEV_URL;
    return url.includes('localhost') || url.includes('127.0.0.1');
  }

  // Client-side check
  if (typeof window !== 'undefined') {
    return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  }

  return false;
}

/**
 * Get the API endpoint URL for a given path.
 * @param path - API path (e.g., '/auth/login')
 * @returns Full API URL
 */
export function getApiUrl(path: string): string {
  const baseUrl = API_BASE_URL;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
}

/**
 * Get the SSR endpoint URL for a given path (server-side rendering).
 * @param path - API path (e.g., '/auth/login')
 * @returns Full SSR URL
 */
export function getSsrUrl(path: string): string {
  const baseUrl = getSsrBaseUrl();
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
}

export const apiConfig = {
  apiBaseUrl: API_BASE_URL,
  ssrBaseUrl: getSsrBaseUrl(),
  isDevelopment: isDevelopmentEnvironment(),
  getApiUrl,
  getSsrUrl,
};
