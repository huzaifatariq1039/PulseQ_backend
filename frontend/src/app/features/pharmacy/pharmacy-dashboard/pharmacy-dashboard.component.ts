import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-pharmacy-dashboard',
    standalone: true,
    imports: [CommonModule, RouterModule, CardModule, ButtonModule, MessageModule, ToastModule, PharmacySidebarComponent],
    templateUrl: './pharmacy-dashboard.component.html',
    styleUrls: ['./pharmacy-dashboard.component.css']
})
export class PharmacyDashboardComponent implements OnInit {
    totalMedicines = 0;
    lowStockCount = 0;
    expiredCount = 0;
    activeCount = 0;
    inventoryValue = 0;

    medicines: Medicine[] = [];
    private sub: Subscription | null = null;

    constructor(
        private pharmacyService: PharmacyService,
        private authService: AuthService,
        private router: Router
    ) { }

    ngOnInit(): void {
        this.sub = this.pharmacyService.medicines$.subscribe(meds => {
            this.medicines = meds;
            this.updateStats();
        });
        
        // Trigger a fresh fetch from the API using correct hospital ID and Staff endpoint
        const hid = (this.authService.getCurrentUser() as any)?.hospitalId || '';
        this.pharmacyService.loadMedicinesFromApi(hid);
    }

    ngOnDestroy(): void {
        this.sub?.unsubscribe();
    }

    updateStats(): void {
        this.totalMedicines = this.medicines.length;
        const today = new Date();
        // Low stock threshold: quantity less than 10
        this.lowStockCount = this.medicines.filter(m => m.quantity < 10).length;
        this.expiredCount = this.medicines.filter(m => new Date(m.expiryDate) < today).length;
        this.activeCount = this.medicines.filter(m => this.getMedicineStatus(m) === 'Active').length;
        this.inventoryValue = this.medicines.reduce((sum, m) => sum + (m.quantity * m.sellingPrice), 0);
    }

    getMedicineStatus(medicine: Medicine): 'Active' | 'Low Stock' | 'Expired' {
        const today = new Date();
        const expiry = new Date(medicine.expiryDate);
        if (expiry < today) return 'Expired';
        if (medicine.quantity < 10) return 'Low Stock';
        return 'Active';
    }

    formatRs(amount: number): string {
        return `Rs ${amount.toFixed(2)}`;
    }

    goToInventory(): void {
        this.router.navigate(['/inventory']);
    }

    goToSales(): void {
        this.router.navigate(['/sales']);
    }
}
