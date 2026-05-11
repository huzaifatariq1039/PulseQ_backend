import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';
import { pharmacyPath } from '../../../core/utils/portal-path.util';

@Component({
    selector: 'app-pharmacy-dashboard',
    standalone: true,
    imports: [
        CommonModule,
        RouterModule,
        CardModule,
        ButtonModule,
        MessageModule,
        ToastModule,
        PharmacySidebarComponent
    ],
    templateUrl: './pharmacy-dashboard.component.html',
    styleUrls: ['./pharmacy-dashboard.component.css']
})
export class PharmacyDashboardComponent implements OnInit, OnDestroy {

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
        private route: ActivatedRoute,
        private router: Router
    ) { }

    ngOnInit(): void {

        const hid =
            (this.authService.getCurrentUser() as any)?.hospitalId || '';

        // FIX: Call load FIRST so loading() becomes true immediately.
        // The guard in PharmacyService prevents duplicate concurrent calls
        // if other components also call this before the response arrives.
        this.pharmacyService.loadMedicinesFromApi(hid);

        // FIX: filter() skips the initial empty-array emission that fires
        // synchronously when the signal is first observed (before the API
        // responds). Without this, stats briefly show 0 then re-render.
        //
        // We wait until loading is false AND we have data, OR loading is
        // false with an empty array (genuinely no medicines in the system).
        this.sub = this.pharmacyService.medicines$
            .pipe(
                filter(() => !this.pharmacyService.loading())
            )
            .subscribe(meds => {
                this.medicines = meds;
                this.updateStats();
            });
    }

    ngOnDestroy(): void {
        this.sub?.unsubscribe();
    }

    updateStats(): void {

        this.totalMedicines = this.medicines.length;

        const today = new Date();

        this.lowStockCount =
            this.medicines.filter(m => m.quantity < 10).length;

        this.expiredCount =
            this.medicines.filter(
                m => m.expiryDate && new Date(m.expiryDate) < today
            ).length;

        this.activeCount =
            this.medicines.filter(
                m => this.getMedicineStatus(m) === 'Active'
            ).length;

        this.inventoryValue =
            this.medicines.reduce(
                (sum, m) => sum + (m.quantity * m.sellingPrice),
                0
            );
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
        this.router.navigate([pharmacyPath('inventory')]);
    }

    goToSales(): void {
        this.router.navigate([pharmacyPath('sales')]);
    }
}