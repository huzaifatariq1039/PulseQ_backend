import { Component, OnInit, PLATFORM_ID, inject, ChangeDetectorRef } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import * as XLSX from 'xlsx';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { CalendarModule } from 'primeng/calendar';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { ChartModule } from 'primeng/chart';
import { PaginatorModule } from 'primeng/paginator';
import { MessageService } from 'primeng/api';

import { PharmacyService } from '../../../core/services/pharmacy.service';
import { ExternalPosService } from '../../../core/services/external-pos.service';
import { AuthService } from '../../../core/services/auth.service';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-sales-revenue',
    standalone: true,
    imports: [
        CommonModule, FormsModule, RouterModule,
        CardModule, ButtonModule, TableModule, CalendarModule,
        InputTextModule, ToastModule, ChartModule, PaginatorModule,
        PharmacySidebarComponent
    ],
    templateUrl: './sales-revenue.component.html',
    styleUrls: ['./sales-revenue.component.css'],
    providers: [MessageService]
})
export class SalesRevenueComponent implements OnInit {

    activeTab: 'overview' | 'products' = 'overview';

    fromDate: Date = new Date(new Date().setDate(new Date().getDate() - 30));
    toDate: Date = new Date();
    selectedPreset = 'last30';
    fromFocused = false;
    toFocused = false;

    presetOptions = [
        { label: 'Last 7 days', value: 'last7' },
        { label: 'Last 30 days', value: 'last30' },
        { label: 'This month', value: 'thisMonth' },
        { label: 'Last month', value: 'lastMonth' }
    ];

    totalRevenue = 0;
    invoiceCount = 0;
    unitsSold = 0;
    avgOrderValue = 0;

    salesOverTimeData: any = null;
    paymentMethodData: any = null;
    showSalesChart = false;
    showPaymentChart = false;

    lineChartOptions: any = {};
    donutChartOptions: any = {};

    allProducts: any[] = [];
    filteredProducts: any[] = [];
    pagedProducts: any[] = [];

    productSearch = '';
    productRows = 10;
    productFirst = 0;

    isExporting = false;
    allSales: any[] = [];

    private readonly platformId = inject(PLATFORM_ID);
    private cdr = inject(ChangeDetectorRef);

    constructor(
        private pharmacyService: PharmacyService,
        private posService: ExternalPosService,
        private authService: AuthService,
        private messageService: MessageService
    ) { }

    ngOnInit(): void {
        this.salesOverTimeData = null;
        this.paymentMethodData = null;
        this.showSalesChart = false;
        this.showPaymentChart = false;
        this.initChartOptions();
        if (isPlatformBrowser(this.platformId)) {
            this.loadFromApi();
        }
    }

    private getApiPreset(): string {
        const map: Record<string, string> = {
            last7: 'last_7_days',
            last30: 'last_30_days',
            thisMonth: 'this_month',
            lastMonth: 'last_month'
        };
        return map[this.selectedPreset] || 'last_30_days';
    }

    initChartOptions(): void {

        this.lineChartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#111827',
                    titleColor: '#ffffff',
                    bodyColor: '#d1d5db',
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: (ctx: any) =>
                            `Revenue: Rs ${(ctx.parsed.y ?? 0).toLocaleString('en-US', {
                                minimumFractionDigits: 0,
                                maximumFractionDigits: 0
                            })}`
                    }
                }
            },
            layout: { padding: { top: 16, right: 8, left: 0, bottom: 0 } },
            scales: {
                x: {
                    grid: { color: 'rgba(156,163,175,0.15)', drawBorder: false },
                    border: { display: false },
                    ticks: {
                        color: '#9ca3af',
                        font: { size: 11, weight: '500' },
                        maxRotation: 35,
                        autoSkip: true,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    grid: { color: 'rgba(156,163,175,0.15)', drawBorder: false },
                    border: { display: false },
                    beginAtZero: false,
                    ticks: {
                        color: '#9ca3af',
                        font: { size: 11 },
                        callback: (v: any) =>
                            v >= 1000 ? 'Rs ' + (v / 1000).toFixed(0) + 'k' : 'Rs ' + v
                    }
                }
            }
        };

        this.donutChartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx: any) =>
                            ` Rs ${(ctx.parsed ?? 0).toLocaleString('en-US')}`
                    }
                }
            }
        };
    }

    loadFromApi(): void {
        const hid = (this.authService.getCurrentUser() as any)?.hospitalId;
        const preset = this.getApiPreset();

        this.pharmacyService.getSalesOverview(hid, preset).subscribe({
            next: (res: any) => {
                const d = res?.data || res || {};
                this.totalRevenue = d.total_revenue ?? 0;
                this.invoiceCount = d.invoices ?? 0;
                this.unitsSold = d.units_sold ?? 0;
                this.avgOrderValue = d.avg_order_value ?? 0;
                this.cdr.markForCheck();
            },
            error: (err) => console.error('Overview error:', err)
        });

        this.pharmacyService.getSalesOverTime(hid, preset).subscribe({
            next: (res: any) => {
                const data = Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : []);
                if (data.length) this.buildSalesOverTimeChart(data);
                this.cdr.markForCheck();
            },
            error: (err) => console.error('Over-time error:', err)
        });

        this.pharmacyService.getPaymentMethodBreakdown(hid, preset).subscribe({
            next: (res: any) => {
                const breakdown = res?.data?.breakdown || res?.breakdown || [];
                if (breakdown.length) this.buildPaymentMethodChart(breakdown);
                this.cdr.markForCheck();
            },
            error: (err) => console.error('Payment error:', err)
        });

        this.pharmacyService.getTopSellingMedicines(hid, preset, 10).subscribe({
            next: (res: any) => {
                const items = Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : []);
                this.allProducts = items.map((p: any) => ({
                    name: p.medicine_name || p.name || 'Unknown',
                    qtySold: p.units_sold || p.quantity || 0,
                    revenue: p.revenue || 0,
                    profit: p.profit || 0,
                    transactions: p.transactions || 0
                }));
                this.filteredProducts = [...this.allProducts];
                this.updateProductPage();
                this.cdr.markForCheck();
            },
            error: (err) => console.error('Medicines error:', err)
        });
    }

    private buildSalesOverTimeChart(data: any[]): void {
        this.showSalesChart = false;
        this.salesOverTimeData = null;
        this.cdr.detectChanges();

        setTimeout(() => {
            this.salesOverTimeData = {
                labels: data.map((d: any) => d.date || d.label),
                datasets: [{
                    data: data.map((d: any) => d.revenue || 0),
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99,102,241,0.08)',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#6366f1',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointHoverBackgroundColor: '#6366f1',
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 2,
                    fill: true,
                    tension: 0.35
                }]
            };
            this.showSalesChart = true;
            this.cdr.markForCheck();
        }, 0);
    }

    private buildPaymentMethodChart(breakdown: any[]): void {
        this.showPaymentChart = false;
        this.paymentMethodData = null;
        this.cdr.detectChanges();

        setTimeout(() => {
            this.paymentMethodData = {
                labels: breakdown.map((b: any) =>
                    (b.method || 'Unknown').charAt(0).toUpperCase() +
                    (b.method || 'Unknown').slice(1).toLowerCase()
                ),
                datasets: [{
                    data: breakdown.map((b: any) => b.amount || 0),
                    backgroundColor: ['#6366f1', '#22c55e', '#f59e0b', '#3b82f6'],
                    borderWidth: 0
                }]
            };
            this.showPaymentChart = true;
            this.cdr.markForCheck();
        }, 0);
    }

    processTransactions(items: any[]): void {
        this.allSales = items.map((item: any) => ({
            id: item.id || item.sale_id,
            medicineName: item.name || item.medicine_name || item.product_name || 'Unknown',
            quantity: item.quantity || item.qty || 1,
            unitPrice: item.selling_price || item.unit_price || item.price || 0,
            totalAmount: item.total_amount || item.total ||
                ((item.quantity || 1) * (item.selling_price || item.unit_price || 0)),
            paymentMethod: item.payment_method || item.payment_type || 'cash',
            date: new Date(item.sale_date || item.created_at || item.date || Date.now())
        }));
        this.buildChartsFromTransactions();
    }

    buildChartsFromTransactions(): void {
        const byDate: Record<string, number> = {};
        for (const s of this.allSales) {
            const key = new Date(s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            byDate[key] = (byDate[key] || 0) + (s.totalAmount || 0);
        }
        const sortedDates = Object.keys(byDate).slice(-14);

        this.showSalesChart = false;
        this.salesOverTimeData = null;
        this.cdr.detectChanges();

        setTimeout(() => {
            this.salesOverTimeData = {
                labels: sortedDates,
                datasets: [{
                    data: sortedDates.map(d => byDate[d]),
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99,102,241,0.08)',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#6366f1',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    fill: true,
                    tension: 0.35
                }]
            };
            this.showSalesChart = true;
            this.cdr.markForCheck();
        }, 0);

        const byMethod: Record<string, number> = {};
        for (const s of this.allSales) {
            const m = (s.paymentMethod || 'cash').toLowerCase();
            byMethod[m] = (byMethod[m] || 0) + (s.totalAmount || 0);
        }

        this.showPaymentChart = false;
        this.paymentMethodData = null;
        this.cdr.detectChanges();

        setTimeout(() => {
            this.paymentMethodData = {
                labels: Object.keys(byMethod).map(m => m.charAt(0).toUpperCase() + m.slice(1)),
                datasets: [{
                    data: Object.values(byMethod),
                    backgroundColor: ['#6366f1', '#22c55e', '#f59e0b', '#3b82f6'],
                    borderWidth: 0
                }]
            };
            this.showPaymentChart = true;
            this.cdr.markForCheck();
        }, 0);
    }

    getPaymentPct(i: number): string {
        const vals: number[] = this.paymentMethodData?.datasets?.[0]?.data || [];
        const total = vals.reduce((a: number, b: number) => a + b, 0);
        if (!total) return '0';
        return ((vals[i] / total) * 100).toFixed(0);
    }

    applyPreset(preset: string): void {
        this.selectedPreset = preset;
        const now = new Date();
        if (preset === 'last7') {
            this.fromDate = new Date(now); this.fromDate.setDate(now.getDate() - 7);
            this.toDate = new Date(now);
        } else if (preset === 'last30') {
            this.fromDate = new Date(now); this.fromDate.setDate(now.getDate() - 30);
            this.toDate = new Date(now);
        } else if (preset === 'thisMonth') {
            this.fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            this.toDate = new Date(now);
        } else if (preset === 'lastMonth') {
            this.fromDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            this.toDate = new Date(now.getFullYear(), now.getMonth(), 0);
        }
        this.loadFromApi();
    }

    onCustomRangeChange(): void {
        this.selectedPreset = '';
        this.loadFromApi();
    }

    get dateRangeLabel(): string {
        if (!this.fromDate || !this.toDate) return '';
        const fmt = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        return `${fmt(this.fromDate)} – ${fmt(this.toDate)}`;
    }

    onProductSearch(): void {
        const q = this.productSearch.trim().toLowerCase();
        this.filteredProducts = q
            ? this.allProducts.filter(p => p.name.toLowerCase().includes(q))
            : [...this.allProducts];
        this.productFirst = 0;
        this.updateProductPage();
    }

    onProductPageChange(event: any): void {
        this.productFirst = event.first;
        this.productRows = event.rows;
        this.updateProductPage();
    }

    updateProductPage(): void {
        this.pagedProducts = this.filteredProducts.slice(
            this.productFirst,
            this.productFirst + this.productRows
        );
    }

    get productTotals() {
        return this.filteredProducts.reduce(
            (acc, p) => ({
                qty: acc.qty + (p.qtySold || 0),
                revenue: acc.revenue + (p.revenue || 0),
                profit: acc.profit + (p.profit || 0)
            }),
            { qty: 0, revenue: 0, profit: 0 }
        );
    }

    formatRs(amount: number): string {
        return `Rs ${(amount || 0).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        })}`;
    }

    exportToExcel(): void {
        const hid = (this.authService.getCurrentUser() as any)?.hospitalId;
        const preset = this.getApiPreset();
        this.isExporting = true;

        this.pharmacyService.exportSalesExcel(hid, preset).subscribe({
            next: (blob: Blob) => {
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `sales_${new Date().toISOString().split('T')[0]}.xlsx`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                this.messageService.add({ severity: 'success', summary: 'Exported', detail: 'Sales data exported successfully', life: 3000 });
                this.isExporting = false;
            },
            error: () => {
                this.messageService.add({ severity: 'error', summary: 'Export failed', detail: 'Failed to export sales data', life: 3000 });
                this.isExporting = false;
            }
        });
    }

    exportProductsToExcel(): void {
        if (!this.filteredProducts.length) {
            this.messageService.add({ severity: 'warn', summary: 'Nothing to export', detail: 'No products found', life: 3000 });
            return;
        }
        this.isExporting = true;
        try {
            const rows = this.filteredProducts.map(p => ({
                'Product': p.name,
                'Qty Sold': p.qtySold,
                'Revenue (Rs)': p.revenue,
                'Profit (Rs)': p.profit
            }));
            const ws = XLSX.utils.json_to_sheet(rows);
            ws['!cols'] = Object.keys(rows[0]).map(k => ({
                wch: Math.max(k.length, ...rows.map(r => String((r as any)[k] ?? '').length)) + 2
            }));
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Products');
            XLSX.writeFile(wb, `products_report_${new Date().toISOString().split('T')[0]}.xlsx`);
            this.messageService.add({ severity: 'success', summary: 'Exported', detail: `${rows.length} products exported`, life: 3000 });
        } catch {
            this.messageService.add({ severity: 'error', summary: 'Export failed', detail: 'Something went wrong', life: 3000 });
        } finally {
            this.isExporting = false;
        }
    }
}