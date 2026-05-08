import { Component, OnInit, PLATFORM_ID, inject } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import * as XLSX from 'xlsx';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { SelectButtonModule } from 'primeng/selectbutton';
import { CalendarModule } from 'primeng/calendar';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { ExternalPosService } from '../../../core/services/external-pos.service';
import { AuthService } from '../../../core/services/auth.service';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { MessageService } from 'primeng/api';

@Component({
    selector: 'app-sales-revenue',
    standalone: true,
    imports: [
        CommonModule, FormsModule, RouterModule,
        CardModule, ButtonModule, TableModule,
        SelectButtonModule, CalendarModule, InputTextModule,
        ToastModule, PharmacySidebarComponent
    ],
    templateUrl: './sales-revenue.component.html',
    styleUrls: ['./sales-revenue.component.css'],
    providers: [MessageService]
})
export class SalesRevenueComponent implements OnInit {

    selectedOption: string = 'week';
    searchTerm: string = '';
    isExporting: boolean = false;
    sales: any[] = [];
    allSales: any[] = [];
    customRange: Date[] = [];

    todaySales: number = 0;
    weeklySales: number = 0;
    monthlySales: number = 0;
    totalRevenue: number = 0;

    options = [
        { label: 'Today', value: 'today' },
        { label: 'This Week', value: 'week' },
        { label: 'This Month', value: 'month' },
        { label: 'Custom Range', value: 'custom' }
    ];

    private readonly platformId = inject(PLATFORM_ID);

    constructor(
        private pharmacyService: PharmacyService,
        private posService: ExternalPosService,
        private authService: AuthService,
        private messageService: MessageService
    ) { }

    ngOnInit(): void {
        // Skip HTTP calls during SSR — this page needs browser auth token
        if (isPlatformBrowser(this.platformId)) {
            this.loadFromApi();
        }
    }

    loadFromApi(): void {
        const hid = (this.authService.getCurrentUser() as any)?.hospitalId;

        // 1. Fetch Aggregates from Inventory Turnover Report
        this.pharmacyService.getInventoryTurnoverReport(hid).subscribe({
            next: (res: any) => {
                const data = res?.data || res || {};
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
            error: () => {}
        });

        // 2. Try daily sales report — may contain transaction data and today's sales
        this.pharmacyService.getDailySalesReport(hid).subscribe({
            next: (res: any) => {
                const data = res?.data || res || {};
                if (data.total_sales || data.today_sales || data.total_amount) {
                    this.todaySales = data.total_sales ?? data.today_sales ?? data.total_amount;
                }
                const txns = data.transactions || data.items || data.sales;
                if (Array.isArray(txns) && txns.length > 0) {
                    this.processTransactions(txns);
                    return;
                }
                // If no transactions, fall through to sales history endpoint
                this.loadSalesHistory(hid);
            },
            error: () => this.loadSalesHistory(hid)
        });
    }

    private loadSalesHistory(hid?: string): void {
        // 3. Try POS sales history endpoint (contains actual sale records with dates & prices)
        this.posService.getSalesHistory(hid).subscribe({
            next: (res: any) => {
                const items = res?.sales || res?.history || res?.data || (Array.isArray(res) ? res : []);
                if (Array.isArray(items) && items.length > 0) {
                    this.processTransactions(items);
                }
            },
            error: () => {}
        });
    }

    processTransactions(items: any[]): void {
        this.allSales = items.map((item: any) => ({
            id:           item.id || item.product_id || item.sale_id,
            medicineName: item.name || item.medicine_name || item.product_name || 'Unknown',
            salt:         item.generic_name || item.salt || '',
            customer:     item.customer || item.patient_name || 'Walk-in',
            quantity:     item.quantity || item.qty || 1,
            unitPrice:    item.selling_price || item.unit_price || item.price || 0,
            totalAmount:  item.total_amount || item.total ||
                          ((item.quantity || 1) * (item.selling_price || item.unit_price || item.price || 0)),
            date: new Date(item.sale_date || item.created_at || item.date || Date.now())
        }));

        this.refreshMetrics();
        this.applyFilter();
    }

    refreshMetrics(): void {
        if (!this.todaySales) this.todaySales = this.calculateTodaySales();
        if (!this.weeklySales) this.weeklySales = this.calculateWeeklySales();
        if (!this.monthlySales) this.monthlySales = this.calculateMonthlySales();
        if (!this.totalRevenue) this.totalRevenue = this.calculateTotalRevenue();
    }

    onPeriodChange(): void {
        this.customRange = [];
        this.applyFilter();
    }

    onCustomRangeChange(): void {
        if (this.customRange?.[0] && this.customRange?.[1]) {
            this.applyFilter();
        }
    }

    applyFilter(): void {
        const now = new Date();
        let filtered = [...(this.allSales || [])];

        if (this.selectedOption === 'today') {
            filtered = filtered.filter(s => new Date(s.date).toDateString() === now.toDateString());
        } else if (this.selectedOption === 'week') {
            const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 7);
            filtered = filtered.filter(s => new Date(s.date) >= weekAgo);
        } else if (this.selectedOption === 'month') {
            const monthAgo = new Date(now); monthAgo.setMonth(now.getMonth() - 1);
            filtered = filtered.filter(s => new Date(s.date) >= monthAgo);
        } else if (this.selectedOption === 'custom') {
            if (this.customRange?.[0] && this.customRange?.[1]) {
                const start = new Date(this.customRange[0]);
                const end   = new Date(this.customRange[1]); end.setHours(23, 59, 59, 999);
                filtered = filtered.filter(s => { const d = new Date(s.date); return d >= start && d <= end; });
            }
        }

        if (this.searchTerm?.trim()) {
            filtered = filtered.filter(s =>
                s.medicineName.toLowerCase().includes(this.searchTerm.trim().toLowerCase())
            );
        }
        this.sales = filtered;
    }

    onSearch(): void { this.applyFilter(); }

    calculateTodaySales(): number {
        const now = new Date();
        return (this.allSales || [])
            .filter(s => new Date(s.date).toDateString() === now.toDateString())
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);
    }

    calculateWeeklySales(): number {
        const weekAgo = new Date(); weekAgo.setDate(weekAgo.getDate() - 7);
        return (this.allSales || [])
            .filter(s => new Date(s.date) >= weekAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);
    }

    calculateMonthlySales(): number {
        const monthAgo = new Date(); monthAgo.setMonth(monthAgo.getMonth() - 1);
        return (this.allSales || [])
            .filter(s => new Date(s.date) >= monthAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);
    }

    calculateTotalRevenue(): number {
        return (this.allSales || []).reduce((sum, s) => sum + (s.totalAmount || 0), 0);
    }

    /** Week-over-week growth % (this week vs previous week) */
    get weeklyGrowth(): number {
        const now = new Date();
        const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 7);
        const twoWeeksAgo = new Date(now); twoWeeksAgo.setDate(now.getDate() - 14);

        const thisWeek = (this.allSales || [])
            .filter(s => new Date(s.date) >= weekAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);

        const prevWeek = (this.allSales || [])
            .filter(s => new Date(s.date) >= twoWeeksAgo && new Date(s.date) < weekAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);

        if (prevWeek === 0) return thisWeek > 0 ? 100 : 0;
        return Math.round(((thisWeek - prevWeek) / prevWeek) * 100);
    }

    /** Month-over-month growth % (this month vs previous month) */
    get monthlyGrowth(): number {
        const now = new Date();
        const monthAgo = new Date(now); monthAgo.setMonth(now.getMonth() - 1);
        const twoMonthsAgo = new Date(now); twoMonthsAgo.setMonth(now.getMonth() - 2);

        const thisMonth = (this.allSales || [])
            .filter(s => new Date(s.date) >= monthAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);

        const prevMonth = (this.allSales || [])
            .filter(s => new Date(s.date) >= twoMonthsAgo && new Date(s.date) < monthAgo)
            .reduce((sum, s) => sum + (s.totalAmount || 0), 0);

        if (prevMonth === 0) return thisMonth > 0 ? 100 : 0;
        return Math.round(((thisMonth - prevMonth) / prevMonth) * 100);
    }

    formatRs(amount: number): string {
        return `Rs ${(amount || 0).toFixed(2)}`;
    }

    exportToExcel(): void {
        if (!this.sales || this.sales.length === 0) {
            this.messageService.add({ severity: 'warn', summary: 'Nothing to export', detail: 'No transactions found', life: 3000 });
            return;
        }
        this.isExporting = true;
        try {
            const exportData = this.sales.map(t => ({
                'Date': new Date(t.date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' }),
                'Medicine Name': t.medicineName || '-',
                'Quantity Sold': t.quantity ?? 0,
                'Unit Price (Rs)': t.unitPrice ?? 0,
                'Total Amount (Rs)': t.totalAmount ?? 0
            }));
            const ws = XLSX.utils.json_to_sheet(exportData);
            ws['!cols'] = Object.keys(exportData[0]).map(key => ({
                wch: Math.max(key.length, ...exportData.map(r => String((r as any)[key] ?? '').length)) + 2
            }));
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Sales');
            XLSX.writeFile(wb, `sales_${this.selectedOption}_${new Date().toISOString().split('T')[0]}.xlsx`);
            this.messageService.add({ severity: 'success', summary: 'Exported', detail: `${exportData.length} row(s) exported`, life: 3000 });
        } catch {
            this.messageService.add({ severity: 'error', summary: 'Export failed', detail: 'Something went wrong', life: 3000 });
        } finally {
            this.isExporting = false;
        }
    }
}