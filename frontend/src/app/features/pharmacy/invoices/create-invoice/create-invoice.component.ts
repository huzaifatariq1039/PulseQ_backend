import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { BreadcrumbModule } from 'primeng/breadcrumb';
import { PanelModule } from 'primeng/panel';
import { TableModule } from 'primeng/table';
import { AutoCompleteModule } from 'primeng/autocomplete';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { FloatLabelModule } from 'primeng/floatlabel';
import { MessageService } from 'primeng/api';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { InvoiceService } from '../../../../core/services/invoice.service';
import { Invoice, InvoiceItem } from '../../../../shared/models/invoice.model';
import { PharmacySidebarComponent } from '../../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-create-invoice',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        CardModule, ButtonModule, InputTextModule, InputNumberModule,
        DropdownModule, ToastModule, TooltipModule, BreadcrumbModule,
        PanelModule, TableModule, AutoCompleteModule, InputTextareaModule,
        FloatLabelModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService],
    templateUrl: './create-invoice.component.html',
    styleUrls: ['./create-invoice.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class CreateInvoiceComponent implements OnInit {
    isEditMode = false;
    isViewMode = false;
    invoiceId: string | null = null;
    isSubmitting = false;
    customerName = 'Walk in customer';
    customerSuggestions: string[] = [];
    invoiceItems: InvoiceItem[] = [];
    subtotal = 0;
    taxPercent = 0;
    discount = 0;
    totalAmount = 0;
    paymentMethod = 'cash';
    status = 'pending';
    notes = '';
    breadcrumbs: any[] = [];
    paymentMethods = [
        { label: 'Cash', value: 'cash' },
        { label: 'Card', value: 'card' },
        { label: 'Online', value: 'online' },
        { label: 'Other', value: 'other' }
    ];
    statuses = [
        { label: 'Pending', value: 'pending' },
        { label: 'Completed', value: 'completed' },
        { label: 'Partial', value: 'partial' },
        { label: 'Cancel', value: 'cancel' }
    ];
    private readonly destroyRef = inject(DestroyRef);

    constructor(
        private invoiceService: InvoiceService,
        private messageService: MessageService,
        private router: Router,
        private route: ActivatedRoute,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.route.queryParams.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
            if (params['id']) {
                this.invoiceId = params['id'];
                const mode = params['mode'] || 'edit';
                this.isEditMode = mode === 'edit';
                this.isViewMode = mode === 'view';
                this.loadInvoice(params['id']);
            } else {
                this.isEditMode = false;
                this.isViewMode = false;
                this.initializeNewInvoice();
            }
            this.cdr.markForCheck();
        });
    }

    loadInvoice(id: string): void {
        this.invoiceService.getInvoice(id).subscribe({
            next: (res) => {
                const invoice = res.data;
                this.customerName = invoice.customer_name;
                this.invoiceItems = invoice.items || [];
                this.discount = invoice.discount || 0;
                this.taxPercent = invoice.tax || 0;
                this.paymentMethod = invoice.payment_method;
                this.status = invoice.status;
                this.notes = invoice.notes || '';
                this.recalculate();
                // If in view mode, disable form fields
                if (this.isViewMode) {
                    setTimeout(() => this.disableFormFields(), 100);
                }
                this.cdr.markForCheck();
            },
            error: (err) => {
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to load invoice'
                });
            }
        });
    }

    disableFormFields(): void {
        // Disable all native input fields and textareas
        const inputs = document.querySelectorAll(
            '.page-wrapper input, ' +
            '.page-wrapper textarea'
        );
        inputs.forEach((input: any) => {
            input.setAttribute('readonly', 'readonly');
            input.setAttribute('disabled', 'disabled');
            input.style.backgroundColor = '#f3f4f6';
            input.style.cursor = 'not-allowed';
        });

        // Disable PrimeNG dropdowns and autocomplete
        const primeElements = document.querySelectorAll(
            '.page-wrapper .p-dropdown, ' +
            '.page-wrapper .p-autocomplete, ' +
            '.page-wrapper .p-inputnumber'
        );
        primeElements.forEach((el: any) => {
            el.style.pointerEvents = 'none';
            el.style.opacity = '0.7';
            el.style.backgroundColor = '#f3f4f6';
            const innerInput = el.querySelector('input');
            if (innerInput) {
                innerInput.setAttribute('readonly', 'readonly');
                innerInput.setAttribute('disabled', 'disabled');
                innerInput.style.backgroundColor = '#f3f4f6';
                innerInput.style.cursor = 'not-allowed';
            }
        });

        // Hide add button for new items
        const addItemBtn = document.querySelector('.page-wrapper .add-item-btn') as HTMLElement;
        if (addItemBtn) {
            addItemBtn.style.display = 'none';
        }

        // Hide delete buttons for existing items
        const deleteButtons = document.querySelectorAll('.page-wrapper .delete');
        deleteButtons.forEach((btn: any) => {
            btn.style.display = 'none';
        });
    }

    initializeNewInvoice(): void {
        this.customerName = 'Walk in customer';
        this.invoiceItems = [];
        this.discount = 0;
        this.taxPercent = 0;
        this.paymentMethod = 'cash';
        this.status = 'pending';
        this.notes = '';
        this.addItem();
    }

    searchCustomer(event: any): void {
        this.customerSuggestions = [
            'Walk in customer',
            'John Doe',
            'Jane Smith',
            'Ahmed Khan'
        ];
    }

    addItem(): void {
        this.invoiceItems.push({
            product_id: null,
            product_name: '',
            quantity: 0,
            unit_price: 0,
            discount: 0,
            total: 0
        });
        this.cdr.markForCheck();
    }

    removeItem(index: number): void {
        this.invoiceItems.splice(index, 1);
        this.recalculate();
    }

    onItemSelected(item: InvoiceItem): void {
        this.recalculate();
    }

    recalculate(): void {
        this.invoiceItems.forEach(item => {
            item.total = (item.quantity * item.unit_price) - item.discount;
        });
        this.subtotal = this.invoiceItems.reduce((sum, item) => sum + (item.total || 0), 0);
        const taxAmount = this.subtotal * (this.taxPercent / 100);
        this.totalAmount = this.subtotal + taxAmount - this.discount;
        this.cdr.markForCheck();
    }

    validateForm(): boolean {
        if (!this.customerName || this.customerName.trim() === '') {
            this.messageService.add({ severity: 'warn', summary: 'Validation Error', detail: 'Customer name is required' });
            return false;
        }
        if (this.invoiceItems.length === 0) {
            this.messageService.add({ severity: 'warn', summary: 'Validation Error', detail: 'At least one item is required' });
            return false;
        }
        if (!this.status) {
            this.messageService.add({ severity: 'warn', summary: 'Validation Error', detail: 'Status is required' });
            return false;
        }
        return true;
    }

    buildPayload(): Partial<Invoice> {
        return {
            customer_name: this.customerName,
            payment_method: this.paymentMethod as any,
            status: this.status as any,
            notes: this.notes,
            discount: this.discount,
            tax: this.taxPercent,
            items: this.invoiceItems.map(item => ({
                product_id: item.product_id,
                product_name: item.product_name,
                product_code: item.product_code ?? null,
                quantity: item.quantity,
                unit_price: item.unit_price,
                discount: item.discount,
                total: (item.quantity * item.unit_price) - (item.discount || 0)  // ← added
            }))
        };
    }
    submit(): void {
        if (!this.validateForm()) return;
        this.isSubmitting = true;
        this.cdr.markForCheck();
        const payload = this.buildPayload();
        if (this.isEditMode && this.invoiceId) {
            this.invoiceService.updateInvoice(this.invoiceId, payload).subscribe({
                next: () => {
                    this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Invoice updated successfully' });
                    setTimeout(() => this.router.navigate(['/staff/pharmacy/invoices']), 1500);
                },
                error: (err) => {
                    this.isSubmitting = false;
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.message || 'Failed to update invoice' });
                    this.cdr.markForCheck();
                }
            });
        } else {
            this.invoiceService.createInvoice(payload).subscribe({
                next: () => {
                    this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Invoice created successfully' });
                    setTimeout(() => this.router.navigate(['/staff/pharmacy/invoices']), 1500);
                },
                error: (err) => {
                    this.isSubmitting = false;
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.message || 'Failed to create invoice' });
                    this.cdr.markForCheck();
                }
            });
        }
    }

    submitAndCreateAnother(): void {
        if (!this.validateForm()) return;
        this.isSubmitting = true;
        this.cdr.markForCheck();
        this.invoiceService.createInvoice(this.buildPayload()).subscribe({
            next: () => {
                this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Invoice created. Ready to create another.' });
                this.initializeNewInvoice();
                this.isSubmitting = false;
                this.cdr.markForCheck();
            },
            error: (err) => {
                this.isSubmitting = false;
                this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.message || 'Failed to create invoice' });
                this.cdr.markForCheck();
            }
        });
    }

    cancel(): void {
        this.router.navigate(['/staff/pharmacy/invoices']);
    }
}