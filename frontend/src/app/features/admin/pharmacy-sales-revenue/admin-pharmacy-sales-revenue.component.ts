import { Component, OnInit, PLATFORM_ID, inject } from '@angular/core';
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
import type { Sale } from '../../../core/services/pharmacy.service';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
    selector: 'app-admin-pharmacy-sales-revenue',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterModule, CardModule, ButtonModule, TableModule, SelectButtonModule, CalendarModule, AdminSidebarComponent],
    templateUrl: './admin-pharmacy-sales-revenue.component.html',
    styleUrls: ['./admin-pharmacy-sales-revenue.component.css']
})
export class AdminPharmacySalesRevenueComponent implements OnInit {
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

    private readonly platformId = inject(PLATFORM_ID);
    private pharmacyService = inject(PharmacyService);
    private posService = inject(ExternalPosService);
    private authService = inject(AuthService);

    ngOnInit(): void {
        // Skip HTTP calls during SSR — this page requires browser auth token
        if (isPlatformBrowser(this.platformId)) {
            this.loadApiData();
        }
    }

    private getHospitalId(): string | undefined {
        return (this.authService.getCurrentUser() as any)?.hospitalId;
    }

    private loadApiData(): void {
        const hid = this.getHospitalId();

        // 1. Daily Sales
        this.pharmacyService.getDailySalesReport(hid)
            .pipe(takeUntilDestroyed())
            .subscribe({
                next: (res: any) => {
                    const data = res?.data || res || {};
                    this.todaySales = data.total_sales || data.today_sales || 0;
                },
                error: () => {
                    this.todaySales = 0; // Removed local fallback
                }
            });

        // 2. Inventory Turnover & Aggregate Metrics
        this.pharmacyService.getInventoryTurnoverReport(hid)
            .pipe(takeUntilDestroyed())
            .subscribe({
                next: (res: any) => {
                    const data = res?.data || res || {};
                    this.totalStock = data.total_stock || data.current_stock || 0;
                    this.medicineTypes = data.medicine_types || data.unique_items || 0;
                    this.inventoryValue = data.inventory_value || data.total_value || 0;

                    if (data.weekly_sales || data.weekly_revenue) {
                        this.weeklySales = data.weekly_sales ?? data.weekly_revenue;
                    }
                    if (data.monthly_sales || data.monthly_revenue) {
                        this.monthlySales = data.monthly_sales ?? data.monthly_revenue;
                    }
                    if (data.total_revenue || data.total_value) {
                        this.totalRevenue = data.total_revenue ?? data.total_value;
                    }
                },
                error: () => {
                    this.totalStock = 0;
                    this.medicineTypes = 0;
                    this.inventoryValue = 0;
                }
            });

        // 3. Sales/Items Table
        this.loadTableData();
    }

    private loadTableData(): void {
        const hid = this.getHospitalId();

        if (this.searchTerm && this.searchTerm.trim()) {
            this.pharmacyService.searchMedicineApi(this.searchTerm)
                .pipe(takeUntilDestroyed())
                .subscribe({
                    next: (res: any) => {
                        this.processApiItemsToSales(res?.data || res?.items || res || []);
                    },
                    error: () => this.fallbackLocalSales()
                });
            return;
        }

        // Primary: try daily sales report (real transactions with sale dates)
        this.pharmacyService.getDailySalesReport(hid)
            .pipe(takeUntilDestroyed())
            .subscribe({
                next: (res: any) => {
                    const data = res?.data || res || {};
                    const txns = data.transactions || data.items || data.sales;
                    if (Array.isArray(txns) && txns.length > 0) {
                        this.processApiItemsToSales(txns);
                    } else {
                        // Fallback: sales history endpoint
                        this.posService.getSalesHistory(hid)
                            .pipe(takeUntilDestroyed())
                            .subscribe({
                                next: (r: any) => this.processApiItemsToSales(r?.sales || r?.history || r?.data || r || []),
                                error: () => this.fallbackLocalSales()
                            });
                    }
                },
                error: () => {
                    // Fallback: sales history endpoint
                    this.posService.getSalesHistory(hid)
                        .pipe(takeUntilDestroyed())
                        .subscribe({
                            next: (r: any) => this.processApiItemsToSales(r?.sales || r?.history || r?.data || r || []),
                            error: () => this.fallbackLocalSales()
                        });
                }
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
        // Removed hardcoded local mock data logic
        this.allSales = [];
        this.refreshLocalMetrics();
        this.applyFilter();
    }

    private refreshLocalMetrics(): void {
        // Only calculate these if they weren't fully set by API
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
            const weekAgo = new Date();
            weekAgo.setDate(now.getDate() - 7);
            filtered = filtered.filter(s => new Date(s.date) >= weekAgo);
        } else if (this.selectedOption === 'month') {
            const monthAgo = new Date();
            monthAgo.setMonth(now.getMonth() - 1);
            filtered = filtered.filter(s => new Date(s.date) >= monthAgo);
        } else if (this.selectedOption === 'all') {
            // All time, no filter
        } else if (this.selectedOption === 'custom') {
            if (this.customRange && this.customRange[0] && this.customRange[1]) {
                const start = new Date(this.customRange[0]);
                start.setHours(0, 0, 0, 0);
                const end = new Date(this.customRange[1]);
                end.setHours(23, 59, 59, 999);
                filtered = filtered.filter(s => {
                    const d = new Date(s.date);
                    return d >= start && d <= end;
                });
            }
        }

        // Search filter (in case API didn't filter or we're using fallback)
        if (this.searchTerm && this.searchTerm.trim()) {
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
        // Reload API data if searching so it hits the search endpoint
        this.loadTableData();
    }

    calculateTodaySales(): number {
        const now = new Date();
        return this.allSales
            .filter(s => {
                const d = new Date(s.date);
                return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
            })
            .reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateWeeklySales(): number {
        const now = new Date();
        const weekAgo = new Date();
        weekAgo.setDate(now.getDate() - 7);
        return this.allSales
            .filter(s => new Date(s.date) >= weekAgo)
            .reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateMonthlySales(): number {
        const now = new Date();
        const monthAgo = new Date();
        monthAgo.setMonth(now.getMonth() - 1);
        return this.allSales
            .filter(s => new Date(s.date) >= monthAgo)
            .reduce((sum, s) => sum + s.totalAmount, 0);
    }

    calculateTotalRevenue(): number {
        return this.allSales.reduce((sum, s) => sum + s.totalAmount, 0);
    }

    /** Week-over-week growth % */
    get weeklyGrowth(): number {
        const now = new Date();
        const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 7);
        const twoWeeksAgo = new Date(now); twoWeeksAgo.setDate(now.getDate() - 14);
        const thisWeek = this.allSales.filter(s => new Date(s.date) >= weekAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        const prevWeek = this.allSales.filter(s => new Date(s.date) >= twoWeeksAgo && new Date(s.date) < weekAgo).reduce((sum, s) => sum + s.totalAmount, 0);
        if (prevWeek === 0) return thisWeek > 0 ? 100 : 0;
        return Math.round(((thisWeek - prevWeek) / prevWeek) * 100);
    }

    /** Month-over-month growth % */
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
