import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

@Component({
    selector: 'app-staff-landing',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './staff-landing.component.html',
    styleUrls: ['../landing-page/landing-page.component.css'] // reuse existing styles
})
export class StaffLandingComponent {
    constructor(private router: Router) { }

    goTo(role: string) {
        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

        if (isLocalhost) {
            // Local development: navigate into the staff subtree
            this.router.navigate([`/staff/${role}`]);
        } else {
            // Production: redirect to subdomain
            window.location.href = `${protocol}//${role}.pulseq.health`;
        }
    }
}
