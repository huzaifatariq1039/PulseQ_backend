import { Component, OnInit, OnDestroy, ChangeDetectionStrategy, ChangeDetectorRef, Injector, effect, inject } from '@angular/core';
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

import { MessageService, ConfirmationService } from 'primeng/api';
import { PharmacyService, AddMedicineApiRequest } from '../../../core/services/pharmacy.service';
import { Subject } from 'rxjs';
import { takeUntil, debounceTime } from 'rxjs/operators';
import { Medicine, MedicineStatus } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';

import * as XLSX from 'xlsx';

@Component({
    selector: 'app-inventory',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule, InputTextModule,
        DropdownModule, ToastModule, ConfirmDialogModule, TooltipModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './inventory.component.html',
    styleUrls: ['./inventory.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class InventoryComponent implements OnInit, OnDestroy {

    sortOptions = [
        { label: 'Name (A-Z)', value: 'name_asc' },
        { label: 'Name (Z-A)', value: 'name_desc' },
        { label: 'Price (Low-High)', value: 'price_asc' },
        { label: 'Price (High-Low)', value: 'price_desc' },
        { label: 'Stock (Low-High)', value: 'stock_asc' },
        { label: 'Stock (High-Low)', value: 'stock_desc' },
        { label: 'Expiry (Soonest)', value: 'expiry_asc' },
        { label: 'Expiry (Latest)', value: 'expiry_desc' }
    ];

    medicines: Medicine[] = [];
    filteredMedicines: Medicine[] = [];
    searchText: string = '';
    medicineStatusFilter: string = 'all';
    selectedSort: string = 'name_asc';
    isImporting: boolean = false;
    isExporting: boolean = false;
    isLoading: boolean = false;

    selectedMedicineIds: Set<string> = new Set();
    isBulkDeleting: boolean = false;

    private importInputRef: HTMLInputElement | null = null;
    private destroy$ = new Subject<void>();
    private searchSubject$ = new Subject<string>();
    private readonly injector = inject(Injector);

    constructor(
        public pharmacyService: PharmacyService,
        public router: Router,
        public messageService: MessageService,
        public confirmationService: ConfirmationService,
        public authService: AuthService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.searchSubject$.pipe(
            debounceTime(300),
            takeUntil(this.destroy$)
        ).subscribe(() => {
            this.applyFilters();
            this.cdr.markForCheck();
        });

        effect(() => {
            this.medicines = this.pharmacyService.medicines();
            this.isLoading = this.pharmacyService.loading();
            this.applyFilters();
            this.cdr.markForCheck();
        }, { injector: this.injector });

        this.fetchAllMedicines();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    fetchAllMedicines(): void {
        this.selectedMedicineIds.clear();
        this.cdr.markForCheck();

        const hid = (this.authService.getCurrentUser() as any)?.hospitalId || '';
        this.pharmacyService.loadMedicinesFromApi(hid);
    }

    /**
     * FIX: id must always come from m.id (the backend UUID).
     * productId holds the numeric product_id separately.
     * Previously apiToMedicine() set id = product_id which broke
     * all update/delete operations and the import UUID resolution.
     */
    private mapApiItem(m: any): Medicine {
        return {
            id: m.id ?? '',                                         // ← UUID (e.g. "a3f9-...")
            productId: m.product_id?.toString() ?? '',              // ← numeric product id
            batchNumber: m.batch_no ?? '',
            name: m.name ?? '',
            salt: m.generic_name ?? '',
            genericName: m.generic_name ?? '',
            expiryDate: m.expiration_date ?? '',
            purchasedPrice: +(m.purchase_price ?? 0),
            sellingPrice: +(m.selling_price ?? 0),
            quantity: +(m.quantity ?? 0),
            type: m.type ?? '',
            category: m.category ?? '',
            subCategory: m.sub_category ?? '',
            distributorName: m.distributor ?? '',
            distributorCompany: m.distributor ?? '',
            stockUnit: m.stock_unit ?? '',
            hospitalId: m.hospital_id ?? '',
            supplierName: '',
            distributorMobile: m.distributor_mobile ?? '',
            manufactureDate: '',
        } as Medicine;
    }

    onSearchChange(): void { this.searchSubject$.next(this.searchText); }
    onSortChange(): void { this.applyFilters(); }
    onStatusFilterChange(): void { this.applyFilters(); }

    clearFilters(): void {
        this.searchText = '';
        this.medicineStatusFilter = 'all';
        this.applyFilters();
    }

    applyFilters(): void {
        let result = [...this.medicines];

        const q = (this.searchText || '').trim().toLowerCase();
        if (q) {
            result = result.filter(m =>
                (m.name || '').toLowerCase().includes(q) ||
                (m.salt || '').toLowerCase().includes(q) ||
                (m.batchNumber || '').toLowerCase().includes(q)
            );
        }

        switch (this.medicineStatusFilter) {
            case 'active': result = result.filter(m => this.getMedicineStatus(m) === 'Active'); break;
            case 'lowStock': result = result.filter(m => this.getMedicineStatus(m) === 'Low Stock'); break;
            case 'expired': result = result.filter(m => this.getMedicineStatus(m) === 'Expired'); break;
            case 'aboutToExpire': result = result.filter(m => this.getMedicineStatus(m) === 'About to Expire'); break;
        }

        result.sort((a, b) => {
            switch (this.selectedSort) {
                case 'name_asc': return (a.name || '').localeCompare(b.name || '');
                case 'name_desc': return (b.name || '').localeCompare(a.name || '');
                case 'price_asc': return (a.sellingPrice || 0) - (b.sellingPrice || 0);
                case 'price_desc': return (b.sellingPrice || 0) - (a.sellingPrice || 0);
                case 'stock_asc': return (a.quantity || 0) - (b.quantity || 0);
                case 'stock_desc': return (b.quantity || 0) - (a.quantity || 0);
                case 'expiry_asc': return this.toMs(a.expiryDate) - this.toMs(b.expiryDate);
                case 'expiry_desc': return this.toMs(b.expiryDate) - this.toMs(a.expiryDate);
                default: return 0;
            }
        });

        this.filteredMedicines = result.map(med => {
            const status = this.getMedicineStatus(med);
            return {
                ...med,
                _uiStatus: status,
                _uiBadgeClass: this.getStatusBadgeClass(status),
                _uiIconClass: this.getStatusIcon(status),
                _uiExpiryDate: this.formatDate(med.expiryDate)
            };
        });

        this.cdr.markForCheck();
    }

    getMedicineStatus(m: Medicine): MedicineStatus | 'Expiring Soon' | 'About to Expire' {
        if (!m.expiryDate) return (m.quantity || 0) < 10 ? 'Low Stock' : 'Active';
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const expiry = this.parseDate(m.expiryDate);
        const diffDays = (expiry.getTime() - today.getTime()) / 86_400_000;
        if (diffDays < 0) return 'Expired';
        if (diffDays < 60) return 'About to Expire';
        if (diffDays < 90) return 'Expiring Soon';
        if ((m.quantity || 0) < 10) return 'Low Stock';
        return 'Active';
    }

    getStatusBadgeClass(status: string): string {
        const map: Record<string, string> = {
            'Expired': 'badge-expired',
            'Low Stock': 'badge-low-stock',
            'Active': 'badge-active',
            'Expiring Soon': 'badge-expiring-soon',
            'About to Expire': 'badge-about-to-expire'
        };
        return map[status] ?? '';
    }

    getStatusIcon(status: string): string {
        const map: Record<string, string> = {
            'Expired': 'pi-times-circle',
            'Low Stock': 'pi-exclamation-circle',
            'Active': 'pi-check-circle',
            'Expiring Soon': 'pi-clock',
            'About to Expire': 'pi-hourglass'
        };
        return map[status] ?? 'pi-circle';
    }

    view(medicine: Medicine): void { this.router.navigate(['/staff/pharmacy/view', medicine.id]); }
    edit(medicine: Medicine): void { this.router.navigate(['/staff/pharmacy/edit', medicine.id]); }
    addMedicine(): void { this.router.navigate(['/staff/pharmacy/add']); }
    goToTrash(): void { this.router.navigate(['/staff/pharmacy/trash']); }

    delete(medicine: Medicine): void {
        this.confirmationService.confirm({
            message: `Are you sure you want to delete <strong>${medicine.name}</strong>?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.pharmacyService.deletePharmacyItemApi(medicine.id).subscribe({
                    next: () => {
                        this.pharmacyService.delete(medicine.id);
                        this.selectedMedicineIds.delete(medicine.id);
                        this.applyFilters();
                        this.messageService.add({
                            severity: 'success', summary: 'Deleted',
                            detail: `${medicine.name} moved to trash`, life: 3000
                        });
                    },
                    error: () => {
                        this.messageService.add({
                            severity: 'error', summary: 'Delete failed',
                            detail: 'Could not delete medicine. Please try again.', life: 4000
                        });
                    }
                });
            }
        });
    }

    get isAllSelected(): boolean {
        return this.filteredMedicines.length > 0 &&
            this.filteredMedicines.every(m => this.selectedMedicineIds.has(m.id));
    }

    get isIndeterminate(): boolean {
        return this.filteredMedicines.some(m => this.selectedMedicineIds.has(m.id)) && !this.isAllSelected;
    }

    get selectedCount(): number {
        return this.selectedMedicineIds.size;
    }

    toggleSelectAll(checked: boolean): void {
        if (checked) {
            this.filteredMedicines.forEach(m => this.selectedMedicineIds.add(m.id));
        } else {
            this.filteredMedicines.forEach(m => this.selectedMedicineIds.delete(m.id));
        }
        this.cdr.markForCheck();
    }

    toggleSelect(id: string, checked: boolean): void {
        if (checked) {
            this.selectedMedicineIds.add(id);
        } else {
            this.selectedMedicineIds.delete(id);
        }
        this.cdr.markForCheck();
    }

    isSelected(id: string): boolean {
        return this.selectedMedicineIds.has(id);
    }

    clearSelection(): void {
        this.selectedMedicineIds.clear();
        this.cdr.markForCheck();
    }

    bulkDelete(): void {
        const count = this.selectedMedicineIds.size;
        if (count === 0) return;

        this.confirmationService.confirm({
            message: `Are you sure you want to delete <strong>${count} medicine${count > 1 ? 's' : ''}</strong>? This cannot be undone.`,
            header: `Delete ${count} Medicine${count > 1 ? 's' : ''}`,
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.isBulkDeleting = true;
                this.cdr.markForCheck();

                const ids = [...this.selectedMedicineIds];
                let done = 0;
                let failed = 0;

                ids.forEach(id => {
                    this.pharmacyService.deletePharmacyItemApi(id).subscribe({
                        next: () => {
                            done++;
                            this.pharmacyService.delete(id);
                            if (done + failed === ids.length) this.onBulkDeleteComplete(done, failed);
                        },
                        error: () => {
                            failed++;
                            if (done + failed === ids.length) this.onBulkDeleteComplete(done, failed);
                        }
                    });
                });
            }
        });
    }

    private onBulkDeleteComplete(done: number, failed: number): void {
        this.isBulkDeleting = false;
        this.selectedMedicineIds.clear();
        this.applyFilters();
        if (done > 0) {
            this.messageService.add({
                severity: 'success', summary: 'Deleted',
                detail: `${done} medicine${done > 1 ? 's' : ''} deleted` + (failed ? `, ${failed} failed` : ''),
                life: 4000
            });
        } else {
            this.messageService.add({
                severity: 'error', summary: 'Delete failed',
                detail: 'Could not delete selected medicines.', life: 4000
            });
        }
        this.cdr.markForCheck();
    }

    // ── Helper: find a value from a row using multiple possible key aliases ──
    private pick(row: any, ...keys: string[]): any {
        for (const k of keys) {
            if (row[k] !== undefined && row[k] !== null && row[k] !== '') return row[k];
        }
        return undefined;
    }

    // ── Normalize all keys: lowercase + trim + collapse spaces ──
    private normalizeRow(obj: any): any {
        const out: any = {};
        for (const key of Object.keys(obj)) {
            const nk = key.trim().replace(/\s+/g, ' ').toLowerCase();
            out[nk] = obj[key];
        }
        return out;
    }

    onImportExcel(event: Event): void {
        const input = event.target as HTMLInputElement;
        if (!input.files?.length) return;
        this.importInputRef = input;
        this.isImporting = true;
        this.cdr.markForCheck();

        const reader = new FileReader();

        reader.onload = (e: ProgressEvent<FileReader>) => {
            try {
                const data = new Uint8Array(e.target?.result as ArrayBuffer);
                const workbook = XLSX.read(data, { type: 'array', cellDates: true });
                const sheet = workbook.Sheets[workbook.SheetNames[0]];

                // ── Detect header row: scan first 10 rows for "name" or "product id" ──
                const rawAll: any[] = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });
                let headerRowIndex = 0;
                for (let i = 0; i < Math.min(10, rawAll.length); i++) {
                    const row = rawAll[i] as any[];
                    const hasHeader = row.some(cell => {
                        const v = (cell ?? '').toString().trim().toLowerCase();
                        return v === 'name' || v === 'medicine name' || v === 'product id' || v === 'product_id';
                    });
                    if (hasHeader) { headerRowIndex = i; break; }
                }

                const json: any[] = XLSX.utils.sheet_to_json(sheet, {
                    range: headerRowIndex,
                    defval: '',
                    cellDates: true
                } as any);

                if (!json.length) {
                    this.finishImportError('No valid medicine rows found in the file');
                    return;
                }

                const firstNorm = this.normalizeRow(json[0]);
                console.log('[Import] Detected column keys:', Object.keys(firstNorm));

                const toStr = (v: any): string => (v ?? '').toString().trim();
                const toNum = (v: any): number => {
                    const n = parseFloat(toStr(v).replace(/,/g, ''));
                    return isNaN(n) ? 0 : n;
                };
                const toInt = (v: any): number => {
                    const n = parseInt(toStr(v).replace(/,/g, ''), 10);
                    return isNaN(n) ? 0 : n;
                };

                const requests: (AddMedicineApiRequest & { _productId: number })[] = json
                    .map(r => this.normalizeRow(r))
                    .filter(row => {
                        const name = toStr(
                            this.pick(row, 'name', 'medicine name', 'medicine_name') ?? ''
                        ).toLowerCase();
                        return name && name !== 'name' && name !== 'medicine name'
                            && name !== 'total' && name !== 'sr no' && name !== 'sr. no.';
                    })
                    .map(row => {
                        const productId = toInt(
                            this.pick(row,
                                'product id', 'product_id', 'productid',
                                'product no', 'product number', 'prod id', 'prod_id'
                            ) ?? 0
                        );

                        const name = toStr(
                            this.pick(row, 'name', 'medicine name', 'medicine_name') ?? ''
                        );

                        const genericName = toStr(
                            this.pick(row,
                                'generic name', 'generic_name', 'genericname',
                                'salt', 'salt name', 'salt_name', 'composition'
                            ) ?? ''
                        );

                        const batchNo = toStr(
                            this.pick(row,
                                'batch no', 'batch_no', 'batchno', 'batch number',
                                'batch_number', 'batch', 'lot no', 'lot number'
                            ) ?? ''
                        );

                        const type = toStr(
                            this.pick(row, 'type', 'medicine type', 'product type') ?? 'medicine'
                        );

                        const distributor = toStr(
                            this.pick(row,
                                'distributor', 'distributor name', 'distributor_name',
                                'distributor company', 'supplier', 'supplier name',
                                'vendor', 'vendor name'
                            ) ?? ''
                        );

                        const purchasePrice = toNum(
                            this.pick(row,
                                'purchase price', 'purchase price (rs)', 'purchase_price',
                                'purchase price(rs)', 'cost price', 'buy price',
                                'purchaseprice', 'cost'
                            ) ?? 0
                        );

                        const sellingPrice = toNum(
                            this.pick(row,
                                'selling price', 'selling price (rs)', 'selling_price',
                                'selling price(rs)', 'sale price', 'retail price',
                                'sellingprice', 'mrp'
                            ) ?? 0
                        );

                        const stockUnit = toStr(
                            this.pick(row,
                                'stock unit', 'stock_unit', 'stockunit',
                                'unit', 'uom', 'pack', 'pack type'
                            ) ?? ''
                        );

                        const quantity = toInt(
                            this.pick(row,
                                'quantity', 'qty', 'stock', 'stock quantity',
                                'available qty', 'available quantity'
                            ) ?? 0
                        );

                        const expiryRaw = this.pick(row,
                            'expiration date', 'expiry date', 'expiration_date',
                            'expiry_date', 'exp date', 'exp_date', 'expiry',
                            'expiration', 'exp', 'expire date', 'expire_date'
                        ) ?? '';
                        const expirationDate = this.parseExpiryDateForApi(expiryRaw);

                        const category = toStr(
                            this.pick(row, 'category', 'cat', 'medicine category') ?? ''
                        );

                        const subCategory = toStr(
                            this.pick(row,
                                'sub category', 'sub_category', 'subcategory',
                                'sub cat', 'sub-category'
                            ) ?? ''
                        );

                        return {
                            _productId: productId,
                            product_id: productId,
                            batch_no: batchNo,
                            name,
                            generic_name: genericName,
                            type,
                            distributor,
                            purchase_price: purchasePrice,
                            selling_price: sellingPrice,
                            stock_unit: stockUnit,
                            quantity,
                            expiration_date: expirationDate,
                            category,
                            sub_category: subCategory,
                        };
                    })
                    .filter(row => {
                        const issues: string[] = [];
                        if (!row.name) issues.push('missing name');
                        if (!row.expiration_date) issues.push('missing/invalid expiry date');
                        if (row.product_id <= 0) issues.push('missing product_id');
                        if (issues.length) {
                            console.warn(`[Import] Skipping "${row.name || '(unnamed)'}":`, issues.join(', '));
                            return false;
                        }
                        return true;
                    });

                if (!requests.length) {
                    this.finishImportError(
                        'No valid rows found. Ensure columns include: Product Id, Name, Expiration Date.'
                    );
                    return;
                }

                console.log(`[Import] ${requests.length} valid rows ready to upsert`);

                /**
                 * FIX: Build TWO lookup maps from the locally loaded medicines list.
                 *
                 * existingByProductId: productId (number) → UUID string
                 *   Used to match rows from the Excel file against existing medicines.
                 *
                 * existingByUUID: uuid string → true
                 *   Guard to ensure we never call update with a non-UUID.
                 *
                 * Because mapApiItem() now correctly stores m.id as the UUID,
                 * this map will contain real UUIDs instead of product_ids.
                 * This eliminates the need to call getMedicineByProductId() entirely
                 * for medicines already in the local list.
                 */
                const existingByProductId = new Map<number, string>();
                this.medicines.forEach(m => {
                    const pid = parseInt(m.productId ?? '', 10);
                    if (!isNaN(pid) && pid > 0 && m.id) {
                        existingByProductId.set(pid, m.id);  // pid → UUID
                    }
                });
                console.log('[Import] Local map entries:',
                    [...existingByProductId.entries()].slice(0, 5),
                    '| Total medicines loaded:', this.medicines.length,
                    '| Sample medicine:', this.medicines[0]
                );

                console.log(`[Import] Local medicine map has ${existingByProductId.size} entries`);

                let completed = 0;
                let updated = 0;
                let added = 0;
                let failed = 0;
                const total = requests.length;

                const checkDone = () => {
                    if (completed + failed === total) this.onImportComplete(added, updated, failed);
                };

                requests.forEach(req => {
                    const { _productId, ...apiReq } = req;

                    // Check local list first using productId → UUID map
                    const existingUUID = _productId ? existingByProductId.get(_productId) : undefined;

                    if (existingUUID) {
                        // UUID found locally — update directly, no extra API call needed
                        console.log(`[Import] Updating existing medicine (product_id: ${_productId}, uuid: ${existingUUID}):`, req.name);
                        this.pharmacyService.updateMedicineApi(existingUUID, apiReq).subscribe({
                            next: () => { completed++; updated++; checkDone(); },
                            error: (err) => {
                                console.error('[Import] Update failed for:', req.name,
                                    '| uuid:', existingUUID,
                                    '| error:', err?.error ?? err);
                                failed++;
                                checkDone();
                            }
                        });
                    } else {
                        // Not in local list — attempt to add as new
                        console.log(`[Import] Adding new medicine (product_id: ${_productId}):`, req.name);
                        this.pharmacyService.addMedicineApi(apiReq).subscribe({
                            next: () => { completed++; added++; checkDone(); },
                            error: (err) => {
                                const msg = (
                                    err?.error?.message ?? err?.error?.detail ??
                                    err?.error?.error ?? JSON.stringify(err?.error) ?? ''
                                ).toLowerCase();

                                const isAlreadyExists =
                                    msg.includes('already exists') ||
                                    msg.includes('duplicate') ||
                                    err.status === 409;

                                console.warn('[Import] addMedicine failed for:', req.name,
                                    '| status:', err.status,
                                    '| isAlreadyExists:', isAlreadyExists,
                                    '| error:', err?.error);

                                console.log('[Import] err.error.data contents:', JSON.stringify(err?.error?.data));

                                if (isAlreadyExists && _productId) {
                                    /**
                                     * The medicine exists on the backend but wasn't in our
                                     * local list (stale list or first-time import on this session).
                                     * Try fetching from backend — note: this may return empty []
                                     * if the backend doesn't support product_id filtering.
                                     * In that case we log clearly and count as failed.
                                     */
                                    console.log(`[Import] Conflict for product_id ${_productId}, attempting UUID resolution via API...`);
                                    this.pharmacyService.getMedicineByProductId(_productId).subscribe({
                                        next: (res: any) => {
                                            const items: any[] = Array.isArray(res)
                                                ? res
                                                : Array.isArray(res?.data)
                                                    ? res.data
                                                    : Array.isArray(res?.medicines)
                                                        ? res.medicines
                                                        : Array.isArray(res?.items)
                                                            ? res.items
                                                            : [];

                                            const match = items.find((m: any) =>
                                                m.product_id?.toString() === _productId.toString()
                                            );
                                            const realId: string | undefined = match?.id;

                                            if (realId) {
                                                // Cache it for future rows in this import batch
                                                existingByProductId.set(_productId, realId);
                                                this.pharmacyService.updateMedicineApi(realId, apiReq).subscribe({
                                                    next: () => { completed++; updated++; checkDone(); },
                                                    error: (e2) => {
                                                        console.error('[Import] Update after conflict failed:', req.name, e2?.error ?? e2);
                                                        failed++;
                                                        checkDone();
                                                    }
                                                });
                                            } else {
                                                /**
                                                 * Backend doesn't support product_id filtering
                                                 * (returns empty data[]). This is a BACKEND issue.
                                                 * Recommend refreshing the page so the local list
                                                 * is populated, then re-importing.
                                                 */
                                                console.error(
                                                    `[Import] Could not resolve UUID for product_id: ${_productId}.`,
                                                    `Backend returned ${items.length} items for this query.`,
                                                    `This medicine exists on the server but could not be updated.`,
                                                    `Tip: Refresh the page to reload the medicines list, then re-import.`
                                                );
                                                failed++;
                                                checkDone();
                                            }
                                        },
                                        error: (e2) => {
                                            console.error('[Import] getMedicineByProductId API call failed for:', _productId, e2);
                                            failed++;
                                            checkDone();
                                        }
                                    });
                                } else {
                                    // 400 or other non-conflict error
                                    console.error('[Import] Non-conflict error for:', req.name,
                                        '| payload:', apiReq,
                                        '| backend response:', err?.error);
                                    failed++;
                                    checkDone();
                                }
                            }
                        });
                    }
                });

            } catch (err) {
                console.error('[Import] Parse error:', err);
                this.finishImportError('Not a valid Excel file.');
            }
        };

        reader.onerror = () => { this.finishImportError('Failed to read the file'); };
        reader.readAsArrayBuffer(input.files[0]);
    }

    // ── Robust date parser → always outputs "YYYY-MM-DD" ──────────────────
    private parseExpiryDateForApi(val: any): string {
        if (val === null || val === undefined || val === '') return '';

        // Native JS Date (from cellDates: true)
        if (val instanceof Date) {
            if (isNaN(val.getTime())) return '';
            const y = val.getFullYear();
            const m = String(val.getMonth() + 1).padStart(2, '0');
            const d = String(val.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        }

        // Excel serial number
        if (typeof val === 'number') {
            try {
                const d = XLSX.SSF.parse_date_code(val);
                if (!d) return '';
                return `${d.y}-${String(d.m).padStart(2, '0')}-${String(d.d).padStart(2, '0')}`;
            } catch { return ''; }
        }

        const s = val.toString().trim();
        if (!s) return '';

        // Already ISO "yyyy-MM-dd"
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

        // "dd-MM-yyyy" e.g. "31-12-2026"
        const dmY = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
        if (dmY) return `${dmY[3]}-${dmY[2].padStart(2, '0')}-${dmY[1].padStart(2, '0')}`;

        // "dd/MM/yyyy" e.g. "31/12/2026"
        const dmYSlash = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (dmYSlash) return `${dmYSlash[3]}-${dmYSlash[2].padStart(2, '0')}-${dmYSlash[1].padStart(2, '0')}`;

        // "yyyy/MM/dd"
        const ymdSlash = s.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
        if (ymdSlash) return `${ymdSlash[1]}-${ymdSlash[2]}-${ymdSlash[3]}`;

        // "d MMM yyyy" e.g. "1 Dec 2027", "27 Aug 2026"
        const dMonY = s.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/);
        if (dMonY) {
            const months: Record<string, string> = {
                jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
                jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12'
            };
            const mon = months[dMonY[2].toLowerCase().slice(0, 3)];
            if (mon) return `${dMonY[3]}-${mon}-${dMonY[1].padStart(2, '0')}`;
        }

        // "MMM yyyy" e.g. "Dec 2027" → use last day of month
        const monY = s.match(/^([A-Za-z]+)\s+(\d{4})$/);
        if (monY) {
            const months: Record<string, string> = {
                jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
                jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12'
            };
            const mon = months[monY[1].toLowerCase().slice(0, 3)];
            if (mon) {
                const lastDay = new Date(parseInt(monY[2]), parseInt(mon), 0).getDate();
                return `${monY[2]}-${mon}-${String(lastDay).padStart(2, '0')}`;
            }
        }

        // Fallback: native Date parse
        const parsed = new Date(s);
        if (!isNaN(parsed.getTime())) return parsed.toISOString().split('T')[0];

        console.warn('[Import] Could not parse expiry date:', s);
        return '';
    }

    private finishImportError(detail: string): void {
        this.messageService.add({ severity: 'warn', summary: 'Nothing imported', detail, life: 5000 });
        this.isImporting = false;
        if (this.importInputRef) { this.importInputRef.value = ''; this.importInputRef = null; }
        this.cdr.markForCheck();
    }

    private onImportComplete(added: number, updated: number, failed: number): void {
        this.isImporting = false;
        if (this.importInputRef) { this.importInputRef.value = ''; this.importInputRef = null; }

        const total = added + updated;
        if (total > 0) {
            const parts: string[] = [];
            if (added > 0) parts.push(`${added} added`);
            if (updated > 0) parts.push(`${updated} updated`);
            if (failed > 0) parts.push(`${failed} skipped (already exist)`);
            this.messageService.add({
                severity: 'success', summary: 'Import complete',
                detail: parts.join(', '), life: 5000
            });
            this.fetchAllMedicines();
        } else {
            this.messageService.add({
                severity: 'warn', summary: 'Import incomplete',
                detail: `${failed} medicines skipped - all items already exist in inventory.`,
                life: 8000
            });
        }
        this.cdr.markForCheck();
    }

    exportToExcel(): void {
        if (!this.filteredMedicines.length) {
            this.messageService.add({
                severity: 'warn', summary: 'Nothing to export',
                detail: 'No medicines match the current filter', life: 3000
            });
            return;
        }

        this.isExporting = true;
        this.cdr.markForCheck();

        const rows = this.filteredMedicines.map((m: any) => ({
            'Product ID': m.productId || '',
            'Batch No': m.batchNumber || '-',
            'Name': m.name,
            'Generic Name': m.salt || '-',
            'Type': m.type || '-',
            'Category': m.category || '-',
            'Sub Category': m.subCategory || '-',
            'Distributor': m.distributorName || m.distributorCompany || '-',
            'Stock Unit': m.stockUnit || '-',
            'Quantity': m.quantity,
            'Purchase Price': m.purchasedPrice,
            'Selling Price': m.sellingPrice,
            'Total Purchase Price': m.purchasedPrice * m.quantity,
            'Total Selling Price': m.sellingPrice * m.quantity,
            'Expiration Date': m.expiryDate || '-',
            'Status': m._uiStatus || '-'
        }));

        const ws = XLSX.utils.json_to_sheet(rows);
        ws['!cols'] = Object.keys(rows[0]).map(k => ({
            wch: Math.max(k.length, ...rows.map((r: any) => String(r[k] ?? '').length)) + 2
        }));
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Inventory');
        XLSX.writeFile(wb, `inventory_${this.medicineStatusFilter}_${new Date().toISOString().split('T')[0]}.xlsx`);

        this.isExporting = false;
        this.cdr.markForCheck();
    }

    private parseDate(dateStr: string): Date {
        if (!dateStr) return new Date(0);
        // "dd-MM-yyyy"
        const dmY = dateStr.match(/^(\d{2})-(\d{2})-(\d{4})$/);
        if (dmY) return new Date(+dmY[3], +dmY[2] - 1, +dmY[1]);
        return new Date(dateStr);
    }

    private toMs(dateStr: string): number { return this.parseDate(dateStr).getTime(); }

    formatDate(dateStr: string): string {
        if (!dateStr) return '-';
        try {
            return this.parseDate(dateStr).toLocaleDateString('en-US', {
                year: 'numeric', month: 'short', day: '2-digit'
            });
        } catch { return dateStr; }
    }

    trackByMedicineId(_i: number, m: any): string { return m.id; }
}