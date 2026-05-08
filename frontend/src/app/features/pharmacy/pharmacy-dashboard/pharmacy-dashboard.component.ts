import { ChangeDetectorRef, Component, DestroyRef, Injector, OnInit, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';
import { RealtimeService } from '../../../core/services/realtime.service';

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
    private readonly realtimeService = inject(RealtimeService);
    private readonly destroyRef = inject(DestroyRef);
    private readonly injector = inject(Injector);
    private readonly cdr = inject(ChangeDetectorRef);
    private realtimeRoom: string | null = null;

    constructor(
        private pharmacyService: PharmacyService,
        private authService: AuthService,
        private route: ActivatedRoute,
        private router: Router
    ) { }

    ngOnInit(): void {
        effect(() => {
            this.medicines = this.pharmacyService.medicines();
            this.updateStats();
            this.cdr.markForCheck();
        }, { injector: this.injector });
        
        // Trigger a fresh fetch from the API using correct hospital ID and Staff endpoint
        const hid = (this.authService.getCurrentUser() as any)?.hospitalId || '';
        this.ensureRealtimeConnection(hid);
        this.pharmacyService.loadMedicinesFromApi(hid);
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
        this.router.navigate(['../inventory'], { relativeTo: this.route });
    }

    goToSales(): void {
        this.router.navigate(['../sales'], { relativeTo: this.route });
    }

    private ensureRealtimeConnection(hospitalId: string): void {
        if (!hospitalId) {
            return;
        }

        const room = `hospital_${hospitalId}`;
        if (this.realtimeRoom === room) {
            return;
        }

        this.realtimeRoom = room;
        this.realtimeService.connect(room)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(message => {
                if (message?.type === 'ack') {
                    return;
                }

                this.pharmacyService.loadMedicinesFromApi(hospitalId);
            });
    }
}
