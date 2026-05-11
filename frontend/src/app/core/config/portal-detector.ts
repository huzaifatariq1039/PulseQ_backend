/**
 * Portal Detector - Runtime determination of which portal is active
 * 
 * This utility determines which portal should be loaded based on:
 * 1. The current hostname (e.g., patient.pulseq.health, doctor.pulseq.health)
 * 2. Or the URL path if on a multi-portal domain
 * 3. Defaults to 'main' if no portal is detected
 * 
 * This enables a single build artifact to serve multiple portal applications
 * from different subdomains or paths.
 * 
 * ⚠️ SSR-Safe: Returns 'main' immediately if window is not defined (server-side)
 */

export type PortalType = 'main' | 'patient' | 'doctor' | 'pharmacy' | 'reception' | 'admin' | 'demo';

/**
 * Detects the active portal based on hostname and URL
 * 
 * Subdomain mapping:
 * - patient.pulseq.health -> 'patient'
 * - doctor.pulseq.health -> 'doctor'
 * - pharmacy.pulseq.health -> 'pharmacy'
 * - reception.pulseq.health -> 'reception'
 * - admin.pulseq.health -> 'admin'
 * - demo.pulseq.health -> 'demo'
 * - pulseq.health / www.pulseq.health -> 'main'
 * - localhost:4200 with /patient path -> 'patient'
 * - localhost:4200 with /staff path -> 'main'
 * 
 * ⚠️ Returns 'main' if called during SSR (window is undefined)
 * 
 * @returns The detected portal type
 */
export function detectPortal(): PortalType {
  // ✅ SSR-safe: Return 'main' immediately if window is not available (server-side rendering)
  if (typeof window === 'undefined') {
    return 'main';
  }

  try {
    const hostname = window.location.hostname.toLowerCase();
    const pathname = window.location.pathname;

    // Extract subdomain from hostname
    // Examples: patient.pulseq.health -> 'patient', pulseq.health -> ''
    const parts = hostname.split('.');
    let subdomain = '';

    if (parts.length > 2) {
      // Example: patient.pulseq.health has 3 parts: [patient, pulseq, health]
      subdomain = parts[0];
    } else if (parts.length === 2) {
      // Example: localhost:4200, pulseq.health
      // For these, check the path instead
      subdomain = '';
    }

    // Map subdomain to portal
    const subdomainMap: Record<string, PortalType> = {
      'patient': 'patient',
      'doctor': 'doctor',
      'pharmacy': 'pharmacy',
      'reception': 'reception',
      'admin': 'admin',
      'demo': 'demo'
    };

    if (subdomain && subdomain in subdomainMap) {
      return subdomainMap[subdomain];
    }

    // If no subdomain matched, check the path
    // This handles localhost:4200/patient, localhost:4200/staff/doctor, etc.
    const pathSegments = pathname.split('/').filter(s => s.length > 0);
    
    if (pathSegments.length === 0) {
      return 'main';
    }

    const firstSegment = pathSegments[0].toLowerCase();

    // Exact match for first-level paths
    if (firstSegment in subdomainMap) {
      return subdomainMap[firstSegment];
    }

    // Special case: /staff/xxx paths on main domain should use main portal
    // (landing page will handle routing to doctor, reception, etc. sub-routes)
    if (firstSegment === 'staff') {
      return 'main';
    }

    // Default to main if nothing matches
    return 'main';
  } catch (error) {
    console.warn('Error detecting portal, defaulting to main:', error);
    return 'main';
  }
}

/**
 * Gets the portal name for the current context
 * Used for logging and debugging
 */
export function getPortalName(): string {
  return detectPortal();
}

/**
 * Checks if the current context is a specific portal
 */
export function isPortal(portal: PortalType): boolean {
  return detectPortal() === portal;
}

/**
 * Debug function to log portal detection info
 * Call this in development to understand routing decisions
 */
export function logPortalDetection(): void {
  if (typeof window !== 'undefined') {
    const portal = detectPortal();
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;
    console.log(`[Portal Detection] hostname=${hostname}, pathname=${pathname}, portal=${portal}`);
  }
}
