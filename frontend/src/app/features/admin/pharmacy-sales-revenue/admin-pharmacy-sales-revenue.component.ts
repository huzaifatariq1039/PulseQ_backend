import { Component, OnInit, OnDestroy, PLATFORM_ID, inject } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { SelectButtonModule } from 'primeng/selectbutton';
import { CalendarModule } from 'primeng/calendar';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { ExternalPosService } from '../../../core/services/external-pos.service';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import type { Sale } from '../../../core/services/pharmacy.service';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';
import { Subject, takeUntil } from 'rxjs';

@Component({
    selector: 'app-admin-pharmacy-sales-revenue',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterModule, CardModule, ButtonModule, TableModule, SelectButtonModule, CalendarModule, AdminSidebarComponent],
    templateUrl: './admin-pharmacy-sales-revenue.component.html',
    styleUrls: ['./admin-pharmacy-sales-revenue.component.css']
})
export class AdminPharmacySalesRevenueComponent implements OnInit, OnDestroy {
    todaySales = 0;
    weeklySales = 0;
    monthlySales = 0;
    totalRevenue = 0;
    totalStock = 0;
    medicineTypes = 0;
    inventoryValue = 0;

    options = [
        { label: 'Today', value: 'today' },
        { label: 'This Week', value: 'week' },
        { label: 'This Month', value: 'month' },
        { label: 'All Time', value: 'all' },
        { label: 'Custom Range', value: 'custom' }
    ];
    selectedOption = 'week';
    customRange: Date[] | null = null;
    searchTerm = '';

    allSales: Sale[] = [];
    sales: Sale[] = [];

    private destroy$ = new Subject<void>();

    private readonly platformId = inject(PLATFORM_ID);
    private pharmacyService = inject(PharmacyService);
    private posService = inject(ExternalPosService);
    private staffService = inject(StaffPortalService);
    private authService = inject(AuthService);

    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.loadApiData();
        }
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    private getHospitalId(): string | undefined {
        return (this.authService.getCurrentUser() as any)?.hospitalId;
    }

    private loadApiData(): void {
        const hid = this.getHospitalId();

        // 1. Sales metrics — /api/v1/staff/portal/reports/sales-summary
        this.staffService.getSalesSummary(hid)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    console.log('[PharmacySales] sales-summary response:', res);
                    const data = res?.data || res || {};
                    this.todaySales = data.daily_revenue || data.today_sales || data.total_sales || 0;
                    this.weeklySales = data.weekly_revenue || data.weekly_sales || 0;
                    this.monthlySales = data.monthly_revenue || data.monthly_sales || 0;
                    this.totalRevenue = data.total_revenue || data.total_value || 0;
                },
                error: (err) => {
                    console.error('[PharmacySales] sales-summary error:', err);
                    this.todaySales = this.weeklySales = this.monthlySales = this.totalRevenue = 0;
                }
            });

        // 2. Inventory metrics — /api/v1/staff/pharmacy/dashboard/stats
        this.pharmacyService.getInventoryTurnoverReport(hid)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    console.log('[PharmacySales] dashboard/stats response:', res);
                    const data = res?.data || res || {};
                    this.totalStock = data.total_medicines || data.total_stock || data.current_stock || 0;
                    this.medicineTypes = data.active_medicines || data.medicine_types || data.unique_items || 0;
                    this.inventoryValue = data.inventory_value || data.total_value || 0;
                },
                error: (err) => {
                    console.error('[PharmacySales] dashboard/stats error:', err);
                    this.totalStock = this.medicineTypes = this.inventoryValue = 0;
                }
            });

        // 3. Sales table
        this.loadTableData();
    }

    private loadTableData(): void {
        const hid = this.getHospitalId();

        if (this.searchTerm?.trim()) {
            this.pharmacyService.searchMedicineApi(this.searchTerm)
                .pipe(takeUntil(this.destroy$))
                .subscribe({
                    next: (res: any) => {
                        this.processApiItemsToSales(res?.data || res?.items || res || []);
                    },
                    error: () => this.fallbackLocalSales()
                });
            return;
        }

        // Primary: daily sales report
        this.pharmacyService.getDailySalesReport(hid)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    console.log('[PharmacySales] getDailySalesReport response:', res);
                    const data = res?.data || res || {};
                    const txns = data.transactions || data.items || data.sales;
                    if (Array.isArray(txns) && txns.length > 0) {
                        this.processApiItemsToSales(txns);
                    } else {
                        this.loadSalesHistoryFallback(hid);
                    }
                },
                error: () => this.loadSalesHistoryFallback(hid)
            });
    }

    // Extracted to avoid nested takeUntil pipes
    private loadSalesHistoryFallback(hid: string | undefined): void {
        this.posService.getSalesHistory(hid)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (r: any) => {
                    this.processApiItemsToSales(r?.sales || r?.history || r?.data || r || []);
                },
                error: () => this.fallbackLocalSales()
            });
    }

    private processApiItemsToSales(items: any[]): void {
        if (!Array.isArray(items)) {
            this.fallbackLocalSales();
            return;
        }

        this.allSales = items.map((item: any) => ({
            id: item.id || item.product_id,
            medicineId: item.product_id?.toString() || item.id,
            medicineName: item.name || item.medicine_name || 'Unknown',
            salt: item.generic_name || item.salt || '',
            customer: item.category || 'General',
            quantity: item.quantity || item.stock || 1,
            unitPrice: item.selling_price || item.price || 0,
            totalAmount: (item.quantity || 1) * (item.selling_price || item.price || 0),
            date: item.sale_date || item.transaction_date || item.created_at
                ? new Date(item.sale_date || item.transaction_date || item.created_at)
                : new Date()
        }));

        this.refreshLocalMetrics();
        this.applyFilter();
    }

    private fallbackLocalSales(): void {
        this.allSales = [];
        this.refreshLocalMetrics();
        this.applyFilter();
    }

    private refreshLocalMetrics(): void {
        if (!this.todaySales) this.todaySales = this.calculateTodaySales();
        if (!this.weeklySales) this.weeklySales = this.calculateWeeklySales();
        if (!this.monthlySales) this.monthlySales = this.calculateMonthlySales();
        if (!this.totalRevenue) this.totalRevenue = this.calculateTotalRevenue();
    }

    onPeriodChange(): void {
        this.customRange = null;
        this.applyFilter();
    }

    onCustomRangeChange(): void {
        if (this.customRange && this.customRange[0] && this.customRange[1]) {
            this.applyFilter();
        }
    }

    applyFilter(): void {
        const now = new Date();
        let filtered = [...this.allSales];

        if (this.selectedOption === 'today') {
            filtered = filtered.filter(s => {
                const d = new Date(s.date);
                return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
            });
        } else if (this.selectedOption === 'week') {
            const weekAgo = new Date(); weekAgo.setDate(now.getDate() - 7);
            filtered = filtered.filter(s => new Date(s.date) >= weekAgo);
        } else if (this.selectedOption === 'month') {
            const monthAgo = new Date(); monthAgo.setMonth(now.getMonth() - 1);
            filtered = filtered.filter(s => new Date(s.date) >= monthAgo);
        } else if (this.selectedOption === 'custom') {
            if (this.customRange?.[0] && this.customRange?.[1]) {
                const start = new Date(this.customRange[0]); start.setHours(0, 0, 0, 0);
                const end = new Date(this.customRange[1]); end.setHours(23, 59, 59, 999);
                filtered = filtered.filter(s => { const d = new Date(s.date); return d >= start && d <= end; });
            }
        }
        // 'all' — no filter

        if (this.searchTerm?.trim()) {
            const term = this.searchTerm.trim().toLowerCase();
            filtered = filtered.filter(s =>
                s.medicineName.toLowerCase().includes(term) ||
                (s.salt?.toLowerCase() ?? '').includes(term) ||
                (s.customer?.toLowerCase() ?? '').includes(term)
            );
        }

        this.sales = filtered;
    }

    onSearch(): void {
        this.loadTableData();
    }

    calculateTodaySales(): number {
        const now = new Date();
        return this.allSales
            .filter(s => { const d = new Date(s.date); return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate(); })
            .reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateWeeklySales(): number {
        const weekAgo = new Date(); weekAgo.setDate(new Date().getDate() - 7);
        return this.allSales.filter(s => new Date(s.date) >= weekAgo).reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateMonthlySales(): number {
        const monthAgo = new Date(); monthAgo.setMonth(new Date().getMonth() - 1);
        return this.allSales.filter(s => new Date(s.date) >= monthAgo).reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateTotalRevenue(): number {
        return this.allSales.reduce((sum, s) => sum + s.totalAmount, 0);
    }

    get weeklyGrowth(): number {
        const now = new Date();
        const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 7);
        const twoWeeksAgo = new Date(now); twoWeeksAgo.setDate(now.getDate() - 14);
        const thisWeek = this.allSales.filter(s => new Date(s.date) >= weekAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        const prevWeek = this.allSales.filter(s => new Date(s.date) >= twoWeeksAgo && new Date(s.date) < weekAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        if (prevWeek === 0) return thisWeek > 0 ? 100 : 0;
        return Math.round(((thisWeek - prevWeek) / prevWeek) * 100);
    }

    get monthlyGrowth(): number {
        const now = new Date();
        const monthAgo = new Date(now); monthAgo.setMonth(now.getMonth() - 1);
        const twoMonthsAgo = new Date(now); twoMonthsAgo.setMonth(now.getMonth() - 2);
        const thisMonth = this.allSales.filter(s => new Date(s.date) >= monthAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        const prevMonth = this.allSales.filter(s => new Date(s.date) >= twoMonthsAgo && new Date(s.date) < monthAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        if (prevMonth === 0) return thisMonth > 0 ? 100 : 0;
        return Math.round(((thisMonth - prevMonth) / prevMonth) * 100);
    }

    formatRs(amount: number): string {
        return `Rs ${amount.toFixed(2)}`;
    }
}