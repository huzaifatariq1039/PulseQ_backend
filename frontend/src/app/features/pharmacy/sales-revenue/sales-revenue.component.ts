import { Component, OnInit, PLATFORM_ID, inject } from '@angular/core';
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
        CommonModule,
        FormsModule,
        RouterModule,

        CardModule,
        ButtonModule,
        TableModule,
        CalendarModule,
        InputTextModule,
        ToastModule,
        ChartModule,
        PaginatorModule,

        PharmacySidebarComponent
    ],

    templateUrl: './sales-revenue.component.html',
    styleUrls: ['./sales-revenue.component.css'],

    providers: [MessageService]
})

export class SalesRevenueComponent implements OnInit {

    // ─────────────────────────────────────────
    // TABS
    // ─────────────────────────────────────────

    activeTab: 'overview' | 'products' = 'overview';

    // ─────────────────────────────────────────
    // DATE FILTERS
    // ─────────────────────────────────────────

    fromDate: Date =
        new Date(new Date().setDate(new Date().getDate() - 30));

    toDate: Date = new Date();

    selectedPreset: string = 'last30';

    fromFocused = false;
    toFocused = false;

    presetOptions = [
        { label: 'Last 7 days', value: 'last7' },
        { label: 'Last 30 days', value: 'last30' },
        { label: 'This month', value: 'thisMonth' },
        { label: 'Last month', value: 'lastMonth' }
    ];

    // ─────────────────────────────────────────
    // OVERVIEW STATS
    // ─────────────────────────────────────────

    totalRevenue: number = 0;
    invoiceCount: number = 0;
    unitsSold: number = 0;
    avgOrderValue: number = 0;

    // ─────────────────────────────────────────
    // CHARTS
    // ─────────────────────────────────────────

    salesOverTimeData: any = {};
    paymentMethodData: any = {};

    barChartOptions: any = {};
    donutChartOptions: any = {};

    // ─────────────────────────────────────────
    // PRODUCTS TAB
    // ─────────────────────────────────────────

    allProducts: any[] = [];
    filteredProducts: any[] = [];
    pagedProducts: any[] = [];

    productSearch: string = '';

    productRows: number = 10;
    productFirst: number = 0;

    // ─────────────────────────────────────────
    // MISC
    // ─────────────────────────────────────────

    isExporting: boolean = false;

    allSales: any[] = [];

    private readonly platformId = inject(PLATFORM_ID);

    constructor(
        private pharmacyService: PharmacyService,
        private posService: ExternalPosService,
        private authService: AuthService,
        private messageService: MessageService
    ) { }

    // ─────────────────────────────────────────
    // INIT
    // ─────────────────────────────────────────

    ngOnInit(): void {

        this.initChartOptions();

        if (isPlatformBrowser(this.platformId)) {
            this.loadFromApi();
        }
    }

    // ─────────────────────────────────────────
    // CHART OPTIONS
    // ─────────────────────────────────────────

    initChartOptions(): void {

        this.barChartOptions = {

            responsive: true,
            maintainAspectRatio: false,

            plugins: {

                legend: {
                    display: false
                },

                tooltip: {
                    backgroundColor: '#111827',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    padding: 12,
                    cornerRadius: 8,

                    callbacks: {
                        label: (ctx: any) =>
                            ` Rs ${ctx.parsed.y?.toLocaleString()}`
                    }
                }
            },

            layout: {
                padding: {
                    top: 10,
                    right: 10,
                    left: 0,
                    bottom: 0
                }
            },

            scales: {

                x: {

                    grid: {
                        display: false,
                        drawBorder: false
                    },

                    border: {
                        display: false
                    },

                    ticks: {
                        color: '#9ca3af',

                        font: {
                            size: 11,
                            weight: '500'
                        }
                    }
                },

                y: {

                    display: false,

                    beginAtZero: true,

                    grid: {
                        display: false,
                        drawBorder: false
                    },

                    border: {
                        display: false
                    }
                }
            }
        };

        this.donutChartOptions = {

            responsive: true,
            maintainAspectRatio: false,

            cutout: '72%',

            plugins: {

                legend: {
                    display: false
                },

                tooltip: {
                    callbacks: {
                        label: (ctx: any) =>
                            ` Rs ${ctx.parsed?.toLocaleString()}`
                    }
                }
            }
        };
    }

    // ─────────────────────────────────────────
    // LOAD API DATA
    // ─────────────────────────────────────────

    loadFromApi(): void {

        const hid =
            (this.authService.getCurrentUser() as any)?.hospitalId;

        // OVERVIEW REPORT
        this.pharmacyService
            .getInventoryTurnoverReport(hid)
            .subscribe({

                next: (res: any) => {

                    const data = res?.data || res || {};

                    this.totalRevenue =
                        data.total_revenue ??
                        data.total_value ??
                        0;

                    this.unitsSold =
                        data.units_sold ??
                        data.total_qty ??
                        0;

                    this.invoiceCount =
                        data.invoice_count ??
                        data.total_invoices ??
                        0;

                    this.avgOrderValue =
                        this.invoiceCount
                            ? this.totalRevenue / this.invoiceCount
                            : 0;

                    this.buildChartsFromData(data);
                },

                error: () => { }
            });

        // DAILY SALES
        this.pharmacyService
            .getDailySalesReport(hid)
            .subscribe({

                next: (res: any) => {

                    const data = res?.data || res || {};

                    const txns =
                        data.transactions ||
                        data.items ||
                        data.sales;

                    if (Array.isArray(txns) && txns.length) {

                        this.processTransactions(txns);

                    } else {

                        this.loadSalesHistory(hid);
                    }
                },

                error: () => this.loadSalesHistory(hid)
            });

        // TOP PRODUCTS
        this.pharmacyService
            .getTopSellingProducts?.(hid)
            ?.subscribe({

                next: (res: any) => {

                    const items =
                        res?.data ||
                        res?.products ||
                        (Array.isArray(res) ? res : []);

                    this.allProducts = items.map((p: any) => ({

                        name:
                            p.name ||
                            p.medicine_name ||
                            p.product_name ||
                            'Unknown',

                        qtySold:
                            p.qty_sold ||
                            p.quantity ||
                            0,

                        revenue:
                            p.revenue ||
                            p.total_revenue ||
                            0,

                        profit:
                            p.profit ||
                            p.net_profit ||
                            0
                    }));

                    this.filteredProducts = [...this.allProducts];

                    this.updateProductPage();
                },

                error: () => { }
            });
    }

    // ─────────────────────────────────────────
    // LOAD SALES HISTORY
    // ─────────────────────────────────────────

    private loadSalesHistory(hid?: string): void {

        this.posService
            .getSalesHistory(hid)
            .subscribe({

                next: (res: any) => {

                    const items =
                        res?.sales ||
                        res?.history ||
                        res?.data ||
                        (Array.isArray(res) ? res : []);

                    if (Array.isArray(items) && items.length) {
                        this.processTransactions(items);
                    }
                },

                error: () => { }
            });
    }

    // ─────────────────────────────────────────
    // PROCESS TRANSACTIONS
    // ─────────────────────────────────────────

    processTransactions(items: any[]): void {

        this.allSales = items.map((item: any) => ({

            id:
                item.id ||
                item.sale_id,

            medicineName:
                item.name ||
                item.medicine_name ||
                item.product_name ||
                'Unknown',

            quantity:
                item.quantity ||
                item.qty ||
                1,

            unitPrice:
                item.selling_price ||
                item.unit_price ||
                item.price ||
                0,

            totalAmount:
                item.total_amount ||
                item.total ||
                (
                    (item.quantity || 1) *
                    (item.selling_price || item.unit_price || 0)
                ),

            paymentMethod:
                item.payment_method ||
                item.payment_type ||
                'cash',

            date:
                new Date(
                    item.sale_date ||
                    item.created_at ||
                    item.date ||
                    Date.now()
                )
        }));

        this.buildChartsFromTransactions();
    }

    // ─────────────────────────────────────────
    // BUILD CHARTS FROM API DATA
    // ─────────────────────────────────────────

    buildChartsFromData(data: any): void {

        // SALES OVER TIME
        if (
            data.daily_sales &&
            Array.isArray(data.daily_sales)
        ) {

            this.salesOverTimeData = {

                labels: data.daily_sales.map(
                    (d: any) => d.date || d.label
                ),

                datasets: [{
                    data: data.daily_sales.map(
                        (d: any) => d.total || d.amount || 0
                    ),

                    backgroundColor: '#6366f1',

                    borderRadius: 10,
                    borderSkipped: false,

                    barThickness: 28,
                    maxBarThickness: 32,

                    categoryPercentage: 0.7,
                    barPercentage: 0.9
                }]
            };
        }

        // PAYMENT METHOD
        if (
            data.payment_breakdown &&
            Array.isArray(data.payment_breakdown)
        ) {

            this.paymentMethodData = {

                labels: data.payment_breakdown.map(
                    (p: any) => p.method || p.label
                ),

                datasets: [{
                    data: data.payment_breakdown.map(
                        (p: any) => p.amount || p.total || 0
                    ),

                    backgroundColor: [
                        '#6366f1',
                        '#22c55e',
                        '#f59e0b',
                        '#3b82f6'
                    ],

                    borderWidth: 0
                }]
            };
        }
    }

    // ─────────────────────────────────────────
    // BUILD CHARTS FROM TRANSACTIONS
    // ─────────────────────────────────────────

    buildChartsFromTransactions(): void {

        // SALES OVER TIME

        const byDate: Record<string, number> = {};

        for (const s of this.allSales) {

            const key =
                new Date(s.date).toLocaleDateString(
                    'en-US',
                    {
                        month: 'short',
                        day: 'numeric'
                    }
                );

            byDate[key] =
                (byDate[key] || 0) +
                (s.totalAmount || 0);
        }

        const sortedDates =
            Object.keys(byDate).slice(-14);

        this.salesOverTimeData = {

            labels: sortedDates,

            datasets: [{
                data: sortedDates.map(d => byDate[d]),

                backgroundColor: '#6366f1',

                borderRadius: 10,
                borderSkipped: false,

                barThickness: 28,
                maxBarThickness: 32,

                categoryPercentage: 0.7,
                barPercentage: 0.9
            }]
        };

        // PAYMENT METHOD

        const byMethod: Record<string, number> = {};

        for (const s of this.allSales) {

            const m =
                (s.paymentMethod || 'cash')
                    .toLowerCase();

            byMethod[m] =
                (byMethod[m] || 0) +
                (s.totalAmount || 0);
        }

        this.paymentMethodData = {

            labels: Object.keys(byMethod).map(
                m =>
                    m.charAt(0).toUpperCase() +
                    m.slice(1)
            ),

            datasets: [{
                data: Object.values(byMethod),

                backgroundColor: [
                    '#6366f1',
                    '#22c55e',
                    '#f59e0b',
                    '#3b82f6'
                ],

                borderWidth: 0
            }]
        };
    }

    // ─────────────────────────────────────────
    // PAYMENT %
    // ─────────────────────────────────────────

    getPaymentPct(i: number): string {

        const vals: number[] =
            this.paymentMethodData?.datasets?.[0]?.data || [];

        const total =
            vals.reduce((a: number, b: number) => a + b, 0);

        if (!total) return '0';

        return ((vals[i] / total) * 100).toFixed(0);
    }

    // ─────────────────────────────────────────
    // DATE PRESETS
    // ─────────────────────────────────────────

    applyPreset(preset: string): void {

        this.selectedPreset = preset;

        const now = new Date();

        if (preset === 'last7') {

            this.fromDate = new Date(now);
            this.fromDate.setDate(now.getDate() - 7);

            this.toDate = new Date(now);

        } else if (preset === 'last30') {

            this.fromDate = new Date(now);
            this.fromDate.setDate(now.getDate() - 30);

            this.toDate = new Date(now);

        } else if (preset === 'thisMonth') {

            this.fromDate =
                new Date(now.getFullYear(), now.getMonth(), 1);

            this.toDate = new Date(now);

        } else if (preset === 'lastMonth') {

            this.fromDate =
                new Date(now.getFullYear(), now.getMonth() - 1, 1);

            this.toDate =
                new Date(now.getFullYear(), now.getMonth(), 0);
        }
    }

    onCustomRangeChange(): void {
        this.selectedPreset = '';
    }

    // ─────────────────────────────────────────
    // DATE RANGE LABEL
    // ─────────────────────────────────────────

    get dateRangeLabel(): string {

        if (!this.fromDate || !this.toDate) return '';

        const fmt = (d: Date) =>
            d.toLocaleDateString(
                'en-US',
                {
                    month: 'short',
                    day: 'numeric'
                }
            );

        return `${fmt(this.fromDate)} – ${fmt(this.toDate)}`;
    }

    // ─────────────────────────────────────────
    // PRODUCT SEARCH
    // ─────────────────────────────────────────

    onProductSearch(): void {

        const q =
            this.productSearch
                .trim()
                .toLowerCase();

        this.filteredProducts = q
            ? this.allProducts.filter(
                p => p.name.toLowerCase().includes(q)
            )
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

        this.pagedProducts =
            this.filteredProducts.slice(
                this.productFirst,
                this.productFirst + this.productRows
            );
    }

    // ─────────────────────────────────────────
    // PRODUCT TOTALS
    // ─────────────────────────────────────────

    get productTotals() {

        return this.filteredProducts.reduce(

            (acc, p) => ({

                qty:
                    acc.qty + (p.qtySold || 0),

                revenue:
                    acc.revenue + (p.revenue || 0),

                profit:
                    acc.profit + (p.profit || 0)

            }),

            {
                qty: 0,
                revenue: 0,
                profit: 0
            }
        );
    }

    // ─────────────────────────────────────────
    // FORMAT CURRENCY
    // ─────────────────────────────────────────

    formatRs(amount: number): string {

        return `Rs ${(amount || 0).toLocaleString(
            'en-US',
            {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }
        )}`;
    }

    // ─────────────────────────────────────────
    // EXPORT
    // ─────────────────────────────────────────

    exportToExcel(): void {

        this.messageService.add({
            severity: 'info',
            summary: 'Export',
            detail: 'No data to export yet',
            life: 3000
        });
    }

    exportProductsToExcel(): void {

        if (!this.filteredProducts.length) {

            this.messageService.add({
                severity: 'warn',
                summary: 'Nothing to export',
                detail: 'No products found',
                life: 3000
            });

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

            const ws =
                XLSX.utils.json_to_sheet(rows);

            ws['!cols'] =
                Object.keys(rows[0]).map(k => ({
                    wch:
                        Math.max(
                            k.length,
                            ...rows.map(
                                r => String((r as any)[k] ?? '').length
                            )
                        ) + 2
                }));

            const wb =
                XLSX.utils.book_new();

            XLSX.utils.book_append_sheet(
                wb,
                ws,
                'Products'
            );

            XLSX.writeFile(
                wb,
                `products_report_${new Date()
                    .toISOString()
                    .split('T')[0]}.xlsx`
            );

            this.messageService.add({
                severity: 'success',
                summary: 'Exported',
                detail: `${rows.length} products exported`,
                life: 3000
            });

        } catch {

            this.messageService.add({
                severity: 'error',
                summary: 'Export failed',
                detail: 'Something went wrong',
                life: 3000
            });

        } finally {

            this.isExporting = false;
        }
    }
}