import {
    Component, OnInit, OnDestroy,
    ChangeDetectionStrategy, ChangeDetectorRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { TableModule } from 'primeng/table';
import { MessageService, ConfirmationService } from 'primeng/api';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { AuthService } from '../../../core/services/auth.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { Subject, forkJoin, of, range } from 'rxjs';
import { takeUntil, switchMap, toArray, catchError } from 'rxjs/operators';

@Component({
    selector: 'app-pharmacy-trash',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        PharmacySidebarComponent, InputTextModule,
        DropdownModule, ToastModule, ConfirmDialogModule,
        TableModule
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
    rowsPerPageOptions = [10, 20, 50, 100];

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

    ngOnInit(): void { this.fetchDeleted(); }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ─────────────────────────────────────────────────────────────
    // Load ALL deleted medicines at once using forkJoin
    // This matches the inventory component behavior
    // ─────────────────────────────────────────────────────────────
    fetchDeleted(): void {
        this.isLoading = true;
        this.cdr.markForCheck();

        const hid = (this.authService.getCurrentUser() as any)?.hospitalId || '';

        this.pharmacyService.getDeletedMedicinesApi(hid, 1, 100)
            .pipe(
                takeUntil(this.destroy$),
                switchMap((res: any) => {
                    const firstPage: any[] = res?.data ?? res?.items ?? res?.medicines ?? (Array.isArray(res) ? res : []);
                    const totalPages: number = res?.meta?.total_pages ?? 1;

                    if (totalPages <= 1) {
                        return of(firstPage);
                    }

                    // Load remaining pages
                    const pageRequests = Array.from(
                        { length: totalPages - 1 },
                        (_, i) => this.pharmacyService.getDeletedMedicinesApi(hid, i + 2, 100).pipe(
                            catchError(() => of(null))
                        )
                    );

                    return forkJoin(pageRequests).pipe(
                        switchMap((results: any[]) => {
                            let all = [...firstPage];
                            results.forEach(r => {
                                if (!r) return;
                                const pageData = r?.data ?? r?.items ?? r?.medicines ?? (Array.isArray(r) ? r : []);
                                all = all.concat(pageData);
                            });
                            return of(all);
                        })
                    );
                }),
                catchError(() => {
                    this.messageService.add({
                        severity: 'error', summary: 'Load failed',
                        detail: 'Could not fetch deleted medicines.', life: 4000
                    });
                    return of([]);
                })
            )
            .subscribe({
                next: (allRaw: any[]) => {
                    this.deletedMedicines = allRaw.map(m => this.pharmacyService.apiToMedicine(m));
                    this.selectedIds.clear();
                    this.applySort();
                    this.isLoading = false;
                    this.cdr.markForCheck();
                },
                error: () => {
                    this.isLoading = false;
                    this.cdr.markForCheck();
                }
            });
    }

    applySort(): void {
        let list = [...this.deletedMedicines];

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

    get selectedCount(): number { return this.selectedIds.size; }

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
        this.selectedIds.has(id) ? this.selectedIds.delete(id) : this.selectedIds.add(id);
        this.cdr.markForCheck();
    }

    isSelected(id: string): boolean { return this.selectedIds.has(id); }

    clearSelection(): void {
        this.selectedIds.clear();
        this.cdr.markForCheck();
    }

    // ─────────────────────────────────────────────────────────────
    // Bulk delete uses optimistic deletion for instant UI feedback
    // ─────────────────────────────────────────────────────────────
    deleteSelected(): void {
        const ids = Array.from(this.selectedIds);
        if (!ids.length) return;

        const names = this.deletedMedicines
            .filter(m => ids.includes(m.id))
            .map(m => m.name).join(', ');

        this.confirmationService.confirm({
            message: `Permanently delete <strong>${ids.length} medicine${ids.length > 1 ? 's' : ''}</strong>? This cannot be undone.<br><small style="color:#9ca3af">${names}</small>`,
            header: 'Bulk Permanent Delete',
            icon: 'pi pi-exclamation-triangle',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => {
                this.isBulkDeleting = true;

                // OPTIMISTIC DELETE: Remove from UI immediately
                const deletedMeds = this.deletedMedicines.filter(m => ids.includes(m.id));
                this.deletedMedicines = this.deletedMedicines.filter(m => !ids.includes(m.id));
                this.selectedIds.clear();
                this.applySort();
                this.cdr.markForCheck();

                // Then call API to delete on backend
                forkJoin(ids.map(id => this.pharmacyService.deletePharmacyItemApi(id)))
                    .pipe(takeUntil(this.destroy$))
                    .subscribe({
                        next: () => {
                            this.isBulkDeleting = false;
                            this.messageService.add({
                                severity: 'warn', summary: 'Deleted',
                                detail: `${ids.length} medicine${ids.length > 1 ? 's' : ''} permanently deleted.`, life: 3000
                            });
                            this.cdr.markForCheck();
                        },
                        error: () => {
                            // Rollback on error - re-add the medicines back
                            this.deletedMedicines = [...this.deletedMedicines, ...deletedMeds];
                            this.applySort();
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
        this.pharmacyService.restoreMedicineApi(med.id)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
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
                // OPTIMISTIC DELETE: Remove from UI immediately
                this.deletedMedicines = this.deletedMedicines.filter(m => m.id !== med.id);
                this.selectedIds.delete(med.id);
                this.applySort();
                this.cdr.markForCheck();

                // Then call API to delete on backend
                this.pharmacyService.deletePharmacyItemApi(med.id)
                    .pipe(takeUntil(this.destroy$))
                    .subscribe({
                        next: () => {
                            this.messageService.add({
                                severity: 'warn', summary: 'Deleted',
                                detail: `${med.name} permanently deleted.`, life: 3000
                            });
                        },
                        error: () => {
                            // Rollback on error - re-add the medicine back
                            this.deletedMedicines.push(med);
                            this.applySort();
                            this.cdr.markForCheck();
                            this.messageService.add({
                                severity: 'error', summary: 'Delete failed',
                                detail: 'Could not permanently delete medicine. Please try again.', life: 4000
                            });
                        }
                    });
            }
        });
    }
}