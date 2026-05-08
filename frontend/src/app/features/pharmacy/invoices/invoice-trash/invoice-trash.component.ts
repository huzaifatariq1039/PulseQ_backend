import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';

import { InvoiceService } from '../../../../core/services/invoice.service';
import { Invoice } from '../../../../shared/models/invoice.model';
import { PharmacySidebarComponent } from '../../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-invoice-trash',
    standalone: true,
    imports: [
        CommonModule, FormsModule,
        TableModule, ButtonModule, ToastModule, TooltipModule, TagModule,
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

        this.invoiceService.getTrash().subscribe({
            next: (res) => {
                // Trash API: { success, data: { invoices: [] } } — data has invoices property
                this.trashedInvoices = (res.data as any)?.invoices || res.data || [];
                this.loading = false;
                this.cdr.markForCheck();
            },
            error: (err) => {
                this.loading = false;
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to load trash'
                });
                this.cdr.markForCheck();
            }
        });
    }

    restore(id: string): void {
        this.invoiceService.restoreInvoice(id).subscribe({
            next: () => {
                this.messageService.add({
                    severity: 'success',
                    summary: 'Restored',
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

    getStatusSeverity(status: string): 'success' | 'secondary' | 'info' | 'warning' | 'danger' | 'contrast' | undefined {
        switch (status) {
            case 'completed': return 'success';
            case 'pending': return 'warning';
            case 'partial': return 'info';
            case 'cancel': return 'danger';
            default: return 'info';
        }
    }

    goBack(): void {
        this.router.navigate(['/staff/pharmacy/invoices']);
    }
}