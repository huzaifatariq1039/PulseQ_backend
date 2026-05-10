import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { AuthService } from '../../../../../core/services/auth.service';
import { pharmacyPath } from '../../../../../core/utils/portal-path.util';

@Component({
    selector: 'app-pharmacy-sidebar',
    standalone: true,
    imports: [CommonModule, RouterModule],
    templateUrl: './pharmacy-sidebar.component.html',
    styleUrls: ['./pharmacy-sidebar.component.css']
})
export class PharmacySidebarComponent {
    sidebarOpen = false;
    dashboardPath = pharmacyPath('dashboard');
    inventoryPath = pharmacyPath('inventory');
    salesPath = pharmacyPath('sales');
    addPath = pharmacyPath('add');
    trashPath = pharmacyPath('trash');

    constructor(private router: Router, private authService: AuthService) { }

    signOut(): void {
        this.authService.logout();
        const isLocalhost = window.location.hostname === 'localhost' ||
                            window.location.hostname === '127.0.0.1';
        this.router.navigate([isLocalhost ? '/staff/pharmacy/auth' : '/auth']);
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }
}
