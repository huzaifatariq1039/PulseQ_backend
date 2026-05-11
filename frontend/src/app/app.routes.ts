import { Routes } from '@angular/router';
import { detectPortal, logPortalDetection } from './core/config/portal-detector';

import { patientRoutes } from './routes/patient.routes';
import { doctorRoutes } from './routes/doctor.routes';
import { pharmacyRoutes } from './routes/pharmacy.routes';
import { receptionRoutes } from './routes/reception.routes';
import { adminRoutes } from './routes/admin.routes';
import { demoRoutes } from './routes/demo.routes';
import { mainRoutes } from './routes/main.routes';

const portalRouteMap: Record<string, Routes> = {
    patient: patientRoutes,
    doctor: doctorRoutes,
    pharmacy: pharmacyRoutes,
    reception: receptionRoutes,
    admin: adminRoutes,
    demo: demoRoutes,
    main: mainRoutes,
};

/**
 * Dynamically determine which portal routes to load at runtime.
 * This enables a single build artifact to serve multiple portals
 * from different subdomains (e.g., patient.pulseq.health, doctor.pulseq.health).
 * 
 * Portal detection is based on:
 * 1. Hostname subdomain (e.g., patient.pulseq.health)
 * 2. URL path if multi-portal (e.g., localhost:4200/patient)
 * 3. Defaults to 'main' if no portal detected
 * 4. Returns 'main' if window is undefined (SSR/server-side)
 * 
 * ⚠️ SSR-Safe: detectPortal() returns 'main' when called during server-side rendering
 */
export const routes: Routes = (() => {
  // Only log portal detection in browser environment
  if (typeof window !== 'undefined') {
    logPortalDetection();
  }
  
  const detectedPortal = detectPortal();
  const selectedRoutes = portalRouteMap[detectedPortal];
  
  return selectedRoutes || mainRoutes;
})();