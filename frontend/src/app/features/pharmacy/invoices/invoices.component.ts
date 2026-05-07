import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { TooltipModule } from 'primeng/tooltip';
import { BadgeModule } from 'primeng/badge';
import { TagModule } from 'primeng/tag';
import { BreadcrumbModule } from 'primeng/breadcrumb';
import { SelectButtonModule } from 'primeng/selectbutton';
import { OverlayPanelModule } from 'primeng/overlaypanel';
import { CalendarModule } from 'primeng/calendar';
import { IconFieldModule } from 'primeng/iconfield';
import { MessageService, ConfirmationService } from 'primeng/api';
import { debounceTime, distinctUntilChanged, Subject } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { InvoiceService } from '../../../core/services/invoice.service';
import { Invoice, InvoiceListParams } from '../../../shared/models/invoice.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-invoices',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule, InputTextModule,
        DropdownModule, ToastModule, ConfirmDialogModule, TooltipModule,
        BadgeModule, TagModule, BreadcrumbModule, SelectButtonModule,
        OverlayPanelModule, CalendarModule, IconFieldModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './invoices.component.html',
    styleUrls: ['./invoices.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class InvoicesComponent implements OnInit {
    invoices: Invoice[] = [];
    loading = false;
    selectedInvoices: Invoice[] = [];
    searchTerm = '';
    selectedStatus: string | null = null;
    rowsPerPage = 10;
    statusOptions = [
        { label: 'All', value: null },
        { label: 'Completed', value: 'completed' },
        { label: 'Pending', value: 'pending' },
        { label: 'Partial', value: 'partial' },
        { label: 'Cancelled', value: 'cancel' }
    ];
    dateFrom: Date | null = null;
    dateTo: Date | null = null;
    activeFilterCount = 0;
    breadcrumbs = [{ label: 'Invoices' }, { label: 'List' }];
    private readonly destroyRef = inject(DestroyRef);
    private readonly searchSubject = new Subject<string>();

    constructor(
        private invoiceService: InvoiceService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private router: Router,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.searchSubject.pipe(
            debounceTime(400),
            distinctUntilChanged(),
            takeUntilDestroyed(this.destroyRef)
        ).subscribe(term => {
            this.loadInvoices({ search: term || undefined });
        });
        this.loadInvoices();
    }

    loadInvoices(params?: InvoiceListParams): void {
        this.loading = true;
        this.cdr.markForCheck();
        this.invoiceService.getInvoices(params).subscribe({
            next: (res) => {
                this.invoices = res.data || [];
                this.loading = false;
                this.cdr.markForCheck();
            },
            error: (err) => {
                this.loading = false;
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to load invoices'
                });
                this.cdr.markForCheck();
            }
        });
    }

    onStatusChange(): void {
        this.loadInvoices({ status: this.selectedStatus || undefined });
    }

    onSearchChange(term: string): void {
        this.searchSubject.next(term);
    }

    applyDateFilter(): void {
        const params: InvoiceListParams = {
            date_from: this.dateFrom ? this.dateFrom.toISOString().split('T')[0] : undefined,
            date_to: this.dateTo ? this.dateTo.toISOString().split('T')[0] : undefined
        };
        this.activeFilterCount = (this.dateFrom ? 1 : 0) + (this.dateTo ? 1 : 0);
        this.loadInvoices(params);
    }

    clearDateFilter(): void {
        this.dateFrom = null;
        this.dateTo = null;
        this.activeFilterCount = 0;
        this.loadInvoices();
    }

    getStatusSeverity(status: string): 'success' | 'secondary' | 'info' | 'warning' | 'danger' | 'contrast' | undefined {
        switch (status) {
            case 'completed': return 'success';
            case 'pending': return 'warning';
            case 'partial': return 'info';
            case 'cancel': return 'danger';
            default: return 'info';
        }
    }

    getPaymentSeverity(method: string): 'success' | 'secondary' | 'info' | 'warning' | 'danger' | 'contrast' | undefined {
        switch (method) {
            case 'cash': return 'success';
            case 'card': return 'info';
            case 'online': return 'warning';
            default: return 'secondary';
        }
    }

    viewInvoice(invoice: Invoice): void {
        this.messageService.add({
            severity: 'info',
            summary: 'View Invoice',
            detail: `View detail for invoice ${invoice.invoice_number}`
        });
    }

    editInvoice(invoice: Invoice): void {
        if (invoice.id) {
            this.router.navigate(['/staff/pharmacy/invoices/edit', invoice.id]);
        }
    }

    printInvoice(invoice: Invoice): void {
        this.messageService.add({
            severity: 'info',
            summary: 'Print Invoice',
            detail: `Print invoice ${invoice.invoice_number}`
        });
    }

    goToCreate(): void {
        this.router.navigate(['/staff/pharmacy/invoices/create']);
    }

    goToTrash(): void {
        this.router.navigate(['/staff/pharmacy/invoices/trash']);
    }

    updateStatus(newStatus: string): void {
        const ids = this.selectedInvoices.map(i => i.id).filter(Boolean) as string[];
        if (ids.length === 0) {
            this.messageService.add({
                severity: 'warn',
                summary: 'Warning',
                detail: 'No invoices selected'
            });
            return;
        }
        this.invoiceService.updateInvoiceStatus(ids, newStatus).subscribe({
            next: () => {
                this.messageService.add({
                    severity: 'success',
                    summary: 'Success',
                    detail: 'Invoices updated successfully'
                });
                this.selectedInvoices = [];
                this.loadInvoices();
            },
            error: (err) => {
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to update invoices'
                });
            }
        });
    }

    deleteInvoice(invoice: Invoice): void {
        if (!invoice.id) return;
        this.confirmationService.confirm({
            message: `Are you sure you want to delete invoice ${invoice.invoice_number}?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.invoiceService.deleteInvoice(invoice.id!).subscribe({
                    next: () => {
                        this.messageService.add({
                            severity: 'success',
                            summary: 'Success',
                            detail: 'Invoice deleted successfully'
                        });
                        this.loadInvoices();
                    },
                    error: (err) => {
                        this.messageService.add({
                            severity: 'error',
                            summary: 'Error',
                            detail: err?.error?.message || 'Failed to delete invoice'
                        });
                    }
                });
            }
        });
    }

    getStatusCount(status: string | null): number {
        if (!status) return this.invoices.length;
        return this.invoices.filter(inv => inv.status === status).length;
    }
}