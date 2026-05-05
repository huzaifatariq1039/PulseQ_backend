import { Component, OnInit, OnDestroy, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageService, ConfirmationService } from 'primeng/api';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { AuthService } from '../../../core/services/auth.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
    selector: 'app-pharmacy-trash',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        PharmacySidebarComponent, InputTextModule,
        DropdownModule, ToastModule, ConfirmDialogModule
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './pharmacy-trash.component.html',
    styleUrls: ['./pharmacy-trash.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class PharmacyTrashComponent implements OnInit, OnDestroy {

    deletedMedicines: Medicine[] = [];
    isLoading = false;
    selectedSort = 'recent';

    searchQuery = '';
    filteredMedicines: Medicine[] = [];

    // ── Multi-select state ──
    selectedIds = new Set<string>();
    isBulkDeleting = false;

    sortOptions = [
        { label: 'Recently Deleted', value: 'recent' },
        { label: 'Oldest First', value: 'oldest' },
        { label: 'Name A–Z', value: 'name_asc' },
        { label: 'Name Z–A', value: 'name_desc' }
    ];

    private destroy$ = new Subject<void>();

    constructor(
        private pharmacyService: PharmacyService,
        private authService: AuthService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.fetchDeleted();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    fetchDeleted(): void {
        this.isLoading = true;
        this.cdr.markForCheck();

        const hid = (this.authService.getCurrentUser() as any)?.hospitalId || '';

        this.pharmacyService.getDeletedMedicinesApi(hid)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    const raw: any[] = res?.items ?? res?.data ?? res?.medicines ?? (Array.isArray(res) ? res : []);
                    this.deletedMedicines = raw.map(m => this.pharmacyService.apiToMedicine(m));
                    this.selectedIds.clear();
                    this.applySort();
                    this.isLoading = false;
                    this.cdr.markForCheck();
                },
                error: () => {
                    this.messageService.add({
                        severity: 'error', summary: 'Load failed',
                        detail: 'Could not fetch deleted medicines.', life: 4000
                    });
                    this.isLoading = false;
                    this.cdr.markForCheck();
                }
            });
    }

    applySort(): void {
        let list = [...this.deletedMedicines];

        // ── filter ──
        const q = this.searchQuery.trim().toLowerCase();
        if (q) {
            list = list.filter(m =>
                (m.name || '').toLowerCase().includes(q) ||
                (m.genericName || '').toLowerCase().includes(q) ||
                (m.productId || m.id || '').toString().toLowerCase().includes(q) ||
                (m.batchNumber || '').toLowerCase().includes(q) ||
                (m.category || '').toLowerCase().includes(q) ||
                (m.distributorCompany || '').toLowerCase().includes(q)
            );
        }

        // ── sort ──
        list.sort((a, b) => {
            switch (this.selectedSort) {
                case 'name_asc': return (a.name || '').localeCompare(b.name || '');
                case 'name_desc': return (b.name || '').localeCompare(a.name || '');
                case 'oldest': return (a.deletedOn || '').localeCompare(b.deletedOn || '');
                default: return (b.deletedOn || '').localeCompare(a.deletedOn || '');
            }
        });

        this.filteredMedicines = list;
        this.cdr.markForCheck();
    }

    // ── Selection helpers ──

    get allSelected(): boolean {
        return this.filteredMedicines.length > 0 &&
            this.filteredMedicines.every(m => this.selectedIds.has(m.id));
    }

    get someSelected(): boolean {
        return this.selectedIds.size > 0 && !this.allSelected;
    }

    get selectedCount(): number {
        return this.selectedIds.size;
    }

    toggleSelectAll(event: Event): void {
        const checked = (event.target as HTMLInputElement).checked;
        if (checked) {
            this.filteredMedicines.forEach(m => this.selectedIds.add(m.id));
        } else {
            this.filteredMedicines.forEach(m => this.selectedIds.delete(m.id));
        }
        this.cdr.markForCheck();
    }

    toggleSelectOne(id: string): void {
        if (this.selectedIds.has(id)) {
            this.selectedIds.delete(id);
        } else {
            this.selectedIds.add(id);
        }
        this.cdr.markForCheck();
    }

    isSelected(id: string): boolean {
        return this.selectedIds.has(id);
    }

    clearSelection(): void {
        this.selectedIds.clear();
        this.cdr.markForCheck();
    }

    // ── Bulk delete ──

    deleteSelected(): void {
        const ids = Array.from(this.selectedIds);
        if (!ids.length) return;

        const names = this.deletedMedicines
            .filter(m => ids.includes(m.id))
            .map(m => m.name)
            .join(', ');

        this.confirmationService.confirm({
            message: `Permanently delete <strong>${ids.length} medicine${ids.length > 1 ? 's' : ''}</strong>? This cannot be undone.<br><small style="color:#9ca3af">${names}</small>`,
            header: 'Bulk Permanent Delete',
            icon: 'pi pi-exclamation-triangle',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => {
                this.isBulkDeleting = true;
                this.cdr.markForCheck();

                const requests = ids.map(id => this.pharmacyService.deletePharmacyItemApi(id));

                forkJoin(requests).subscribe({
                    next: () => {
                        this.deletedMedicines = this.deletedMedicines.filter(m => !ids.includes(m.id));
                        this.selectedIds.clear();
                        this.applySort();
                        this.isBulkDeleting = false;
                        this.messageService.add({
                            severity: 'warn', summary: 'Deleted',
                            detail: `${ids.length} medicine${ids.length > 1 ? 's' : ''} permanently deleted.`, life: 3000
                        });
                        this.cdr.markForCheck();
                    },
                    error: () => {
                        this.isBulkDeleting = false;
                        this.messageService.add({
                            severity: 'error', summary: 'Bulk Delete Failed',
                            detail: 'Some items could not be deleted. Please try again.', life: 4000
                        });
                        this.cdr.markForCheck();
                    }
                });
            }
        });
    }

    undoDelete(med: Medicine): void {
        this.pharmacyService.restoreMedicineApi(med.id).subscribe({
            next: () => {
                this.deletedMedicines = this.deletedMedicines.filter(m => m.id !== med.id);
                this.selectedIds.delete(med.id);
                this.applySort();
                this.messageService.add({
                    severity: 'success', summary: 'Restored',
                    detail: `${med.name} has been restored.`, life: 3000
                });
            },
            error: () => {
                this.messageService.add({
                    severity: 'error', summary: 'Restore failed',
                    detail: 'Could not restore medicine. Please try again.', life: 4000
                });
            }
        });
    }

    deletePermanently(med: Medicine): void {
        this.confirmationService.confirm({
            message: `Permanently delete <strong>${med.name}</strong>? This cannot be undone.`,
            header: 'Permanent Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.pharmacyService.deletePharmacyItemApi(med.id).subscribe({
                    next: () => {
                        this.deletedMedicines = this.deletedMedicines.filter(m => m.id !== med.id);
                        this.selectedIds.delete(med.id);
                        this.applySort();
                        this.messageService.add({
                            severity: 'warn', summary: 'Deleted',
                            detail: `${med.name} permanently deleted.`, life: 3000
                        });
                    },
                    error: () => {
                        this.messageService.add({
                            severity: 'error', summary: 'Delete failed',
                            detail: 'Could not permanently delete medicine.', life: 4000
                        });
                    }
                });
            }
        });
    }
}