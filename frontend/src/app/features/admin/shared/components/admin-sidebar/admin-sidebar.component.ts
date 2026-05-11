import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../../../../../core/services/auth.service';

@Component({
    selector: 'app-admin-sidebar',
    standalone: true,
    imports: [CommonModule, RouterModule],
    templateUrl: './admin-sidebar.component.html',
    styleUrls: ['./admin-sidebar.component.css']
})
export class AdminSidebarComponent {
    sidebarOpen = false;

    constructor(private route: ActivatedRoute, private router: Router, private authService: AuthService) { }

    signOut(): void {
        this.authService.logout();
        // route back to admin login page, mimic existing components
        this.router.navigate(['auth'], { relativeTo: this.route.parent?.parent });
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }
}
