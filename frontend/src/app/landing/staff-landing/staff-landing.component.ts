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

        // All staff portals live on their own subdomain
        window.location.href = `${protocol}//${role}.pulseq.health`;
    }
}
