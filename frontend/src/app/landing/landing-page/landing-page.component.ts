import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { isDevelopmentEnvironment } from '../../core/config/api.config';
import { detectPortal } from '../../core/config/portal-detector';

@Component({
  selector: 'app-landing-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './landing-page.component.html',
  styleUrls: ['./landing-page.component.css']
})
export class LandingPageComponent {

  constructor(private router: Router) { }

  /**
   * Navigate to a specific portal application.
   * 
   * For single-build, multi-subdomain architecture:
   * - On localhost/development: use router.navigate (all routes in single build)
   * - On production subdomains: redirect to appropriate subdomain if needed
   * - Within same portal: use router.navigate (respects SPA routing)
   * 
   * @param role The target portal (patient, doctor, pharmacy, reception, admin, demo)
   */
  goTo(role: string): void {
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const hostname = window.location.hostname.toLowerCase();
    const isLocalhost = isDevelopmentEnvironment();
    const currentPortal = detectPortal();

    // Special handling for staff route (always internal navigation)
    if (role === 'staff') {
      this.router.navigate(['/staff']);
      return;
    }

    // Demo portal: always redirect to its own subdomain (has separate build)
    if (role === 'demo') {
      window.location.href = `${protocol}//demo.pulseq.health`;
      return;
    }

    // Development/localhost: all portals available in single build under paths
    // Use internal routing to stay in SPA
    if (isLocalhost) {
      this.router.navigate([`/${role}`]);
      return;
    }

    // Production/subdomains:
    // If requesting the same portal we're already on, just navigate internally
    if (currentPortal === role) {
      // For portal subdomains like patient.pulseq.health:
      // Navigate to root of that portal (which will redirect to auth/dashboard)
      this.router.navigate(['/']);
      return;
    }

    // If requesting a different portal, redirect to that subdomain
    // This causes a full page load where detectPortal() will return the new portal
    window.location.href = `${protocol}//${role}.pulseq.health`;
  }
}