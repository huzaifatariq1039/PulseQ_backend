import { mergeApplicationConfig, ApplicationConfig } from '@angular/core';
import { provideServerRendering } from '@angular/platform-server';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { appConfig } from './app.config';
import { getSsrBaseUrl } from './core/config/api.config';

/**
 * On the server, Node.js cannot resolve relative URLs like /api/v1/...
 * We provide a base URL so the SSR absolute-URL interceptor can prefix requests.
 * 
 * Uses environment variables in order of preference:
 * 1. SSR_BASE_URL (process.env)
 * 2. VITE_SSR_URL
 * 3. Defaults to http://localhost:4000
 */
export const SSR_BASE_URL = getSsrBaseUrl();

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering()
  ]
};

export const config = mergeApplicationConfig(appConfig, serverConfig);
