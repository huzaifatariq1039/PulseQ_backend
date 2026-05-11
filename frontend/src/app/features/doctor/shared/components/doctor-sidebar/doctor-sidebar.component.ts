import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../../../../../core/services/auth.service';

@Component({
    selector: 'app-doctor-sidebar',
    standalone: true,
    imports: [CommonModule, RouterModule],
    templateUrl: './doctor-sidebar.component.html',
    styleUrls: ['./doctor-sidebar.component.css']
})
export class DoctorSidebarComponent {
    sidebarOpen = false;

    constructor(private route: ActivatedRoute, private router: Router, private authService: AuthService) { }

    signOut(): void {
        this.authService.logout();
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }
}