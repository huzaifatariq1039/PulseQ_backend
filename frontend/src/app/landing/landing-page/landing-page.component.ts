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

    if (role === 'staff') {
      // staff page is on the same main domain build
      this.router.navigate(['/staff']);
    } else if (role === 'demo') {
      // demo has its own subdomain
      window.location.href = `${protocol}//demo.pulseq.health`;
    } else {
      // all portals live on their own subdomain
      window.location.href = `${protocol}//${role}.pulseq.health`;
    }
  }
}