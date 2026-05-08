import { mergeApplicationConfig, ApplicationConfig } from '@angular/core';
import { provideServerRendering } from '@angular/platform-server';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { appConfig } from './app.config';

/**
 * On the server, Node.js cannot resolve relative URLs like /api/v1/...
 * We provide a base URL so the SSR absolute-URL interceptor can prefix requests.
 * The port here matches the Express SSR server (default 4000) or your dev proxy.
 */
export const SSR_BASE_URL = process.env['SSR_BASE_URL'] || 'http://localhost:4000';

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering()
  ]
};

export const config = mergeApplicationConfig(appConfig, serverConfig);
