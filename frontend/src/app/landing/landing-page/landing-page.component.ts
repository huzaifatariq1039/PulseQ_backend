import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

@Component({
  selector: 'app-landing-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './landing-page.component.html',
  styleUrls: ['./landing-page.component.css']
})
export class LandingPageComponent {

  constructor(private router: Router) { }

  goTo(role: string) {
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (role === 'staff') {
      // staff page is on the same main domain build
      this.router.navigate(['/staff']);
    } else if (role === 'demo') {
      // demo has its own subdomain
      window.location.href = `${protocol}//demo.pulseq.health`;
    } else if (isLocalhost) {
      // Local development: use route-based navigation
      this.router.navigate([`/${role}`]);
    } else {
      // Production: redirect to subdomain
      window.location.href = `${protocol}//${role}.pulseq.health`;
    }
  }
}