import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../../../../../core/services/auth.service';

@Component({
    selector: 'app-pharmacy-sidebar',
    standalone: true,
    imports: [CommonModule, RouterModule],
    templateUrl: './pharmacy-sidebar.component.html',
    styleUrls: ['./pharmacy-sidebar.component.css']
})
export class PharmacySidebarComponent {
    sidebarOpen = false;

    constructor(private router: Router, private route: ActivatedRoute, private authService: AuthService) { }

    signOut(): void {
        this.authService.logout();
        this.router.navigate(['../auth'], { relativeTo: this.route });
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }
}
