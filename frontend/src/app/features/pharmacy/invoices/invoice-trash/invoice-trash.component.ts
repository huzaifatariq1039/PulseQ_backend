import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { BreadcrumbModule } from 'primeng/breadcrumb';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { Invoice } from '../../../../shared/models/invoice.model';
import { InvoiceService } from '../../../../core/services/invoice.service';
import { PharmacySidebarComponent } from '../../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-invoice-trash',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule,
        ToastModule, BreadcrumbModule, TagModule, TooltipModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService],
    templateUrl: './invoice-trash.component.html',
    styleUrls: ['./invoice-trash.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class InvoiceTrashComponent implements OnInit {
    trashedInvoices: Invoice[] = [];
    loading = false;
    breadcrumbs = [{ label: 'Invoices' }, { label: 'Trash' }];
    private readonly destroyRef = inject(DestroyRef);

    constructor(
        private invoiceService: InvoiceService,
        private messageService: MessageService,
        private router: Router,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.loadTrash();
    }

    loadTrash(): void {
        this.loading = true;
        this.cdr.markForCheck();
        this.invoiceService.getTrash().pipe(
            takeUntilDestroyed(this.destroyRef)
        ).subscribe({
            next: (res) => {
                this.trashedInvoices = res.data || [];
                this.loading = false;
                this.cdr.markForCheck();
            },
            error: (err) => {
                this.loading = false;
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to load trashed invoices'
                });
                this.cdr.markForCheck();
            }
        });
    }

    restore(id: string | undefined): void {
        if (!id) {
            this.messageService.add({
                severity: 'warn',
                summary: 'Warning',
                detail: 'Invalid invoice ID'
            });
            return;
        }
        this.invoiceService.restoreInvoice(id).subscribe({
            next: () => {
                this.messageService.add({
                    severity: 'success',
                    summary: 'Success',
                    detail: 'Invoice restored successfully'
                });
                this.loadTrash();
            },
            error: (err) => {
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to restore invoice'
                });
            }
        });
    }

    goBack(): void {
        this.router.navigate(['/staff/pharmacy/invoices']);
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
}