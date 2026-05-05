import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DoctorService } from '../../../core/services/doctor.service';
import { AuthService } from '../../../core/services/auth.service';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';

import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { RippleModule } from 'primeng/ripple';
import { MessageService, ConfirmationService } from 'primeng/api';

export interface Department {
    id?: string;
    name: string;
    description?: string;
    createdAt?: string;
}

@Component({
    selector: 'app-admin-manage-departments',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        AdminSidebarComponent,
        ButtonModule,
        DialogModule,
        InputTextModule,
        ToastModule,
        ConfirmDialogModule,
        RippleModule
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './admin-manage-departments.component.html',
    styleUrl: './admin-manage-departments.component.css'
})
export class AdminManageDepartmentsComponent implements OnInit, OnDestroy {

    departments: Department[] = [];
    filteredDepartments: Department[] = [];
    searchText = '';

    showAddDialog = false;
    showEditDialog = false;

    addFormModel: Department = { name: '', description: '' };
    editFormModel: Department = { name: '', description: '' };
    editingDepartment: Department | null = null;

    private hospitalId = '';
    private destroy$ = new Subject<void>();

    constructor(
        private doctorService: DoctorService,
        private authService: AuthService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService
    ) { }

    ngOnInit(): void {
        this.hospitalId = this.resolveHospitalId();
        console.log('[DEBUG] Resolved hospital_id:', this.hospitalId);
        this.loadDepartments();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── LOAD ──────────────────────────────────────────────────

    loadDepartments(): void {
        this.doctorService.listAdminDepartments(this.hospitalId || undefined)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    console.log('[DEBUG] Raw departments response:', JSON.stringify(res));

                    // Extract array from any response shape
                    let depts: any[] = [];
                    if (Array.isArray(res)) depts = res;
                    else if (Array.isArray(res?.data)) depts = res.data;
                    else if (Array.isArray(res?.departments)) depts = res.departments;
                    else if (Array.isArray(res?.results)) depts = res.results;

                    this.departments = depts.map((dept: any) => {
                        // Backend currently returns plain strings e.g. "Clinical Psychologist"
                        // Once backend adds IDs, it will return objects and fall into the else branch
                        if (typeof dept === 'string') {
                            return {
                                id: dept,           // using name as temp ID until backend adds UUID
                                name: dept,
                                description: '',
                                createdAt: ''
                            };
                        }
                        // Backend returns objects with real IDs: { id, name, description, ... }
                        return {
                            id: dept.id || dept._id || dept.department_id || dept.name || null,
                            name: dept.name || '',
                            description: dept.description || '',
                            createdAt: dept.created_at || ''
                        };
                    }).filter((d: Department) => d.name); // only filter by name, not id

                    console.log('[DEBUG] Mapped departments:', this.departments);
                    this.applyFilters();
                },
                error: (err: any) => {
                    console.error('Failed to load departments', err);
                    this.showError('Failed to load departments');
                }
            });
    }

    // ── SEARCH ────────────────────────────────────────────────

    onSearchInput(event: Event): void {
        this.searchText = (event.target as HTMLInputElement).value;
        this.applyFilters();
    }

    applyFilters(): void {
        if (!this.searchText?.trim()) {
            this.filteredDepartments = [...this.departments];
            return;
        }
        const term = this.searchText.toLowerCase();
        this.filteredDepartments = this.departments.filter(d =>
            d.name.toLowerCase().includes(term)
        );
    }

    // ── ADD ───────────────────────────────────────────────────

    openAddDialog(): void {
        this.addFormModel = { name: '', description: '' };
        this.showAddDialog = true;
    }

    closeAddDialog(): void {
        this.showAddDialog = false;
        this.addFormModel = { name: '', description: '' };
    }

    addDepartment(): void {
        if (!this.addFormModel.name?.trim()) {
            this.showWarn('Department name is required');
            return;
        }

        if (!this.hospitalId) {
            this.showError('Hospital ID not found. The admin account must have a hospital assigned in the database.');
            return;
        }

        const payload = {
            name: this.addFormModel.name.trim(),
            description: this.addFormModel.description?.trim() || '',
            hospital_id: this.hospitalId
        };

        console.log('[DEBUG] Sending payload:', payload);

        this.doctorService.createDepartment(payload)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    console.log('[DEBUG] Create department response:', res);
                    const newId = res?.id || res?.data?.id || res?.department?.id;

                    if (!newId) {
                        // No ID returned — reload from API to get fresh list
                        this.loadDepartments();
                    } else {
                        this.departments.push({
                            id: newId,
                            name: payload.name,
                            description: payload.description,
                            createdAt: ''
                        });
                        this.applyFilters();
                    }
                    this.showSuccess(`"${payload.name}" added successfully`);
                    this.closeAddDialog();
                },
                error: (err: any) => {
                    console.error('Failed to create department', err);
                    this.showError('Failed to add department');
                }
            });
    }

    // ── EDIT ──────────────────────────────────────────────────

    openEditDialog(dept: Department): void {
        this.editingDepartment = { ...dept };
        this.editFormModel = { ...dept };
        this.showEditDialog = true;
    }

    closeEditDialog(): void {
        this.showEditDialog = false;
        this.editFormModel = { name: '', description: '' };
        this.editingDepartment = null;
    }

    saveDepartment(): void {
        if (!this.editFormModel.name?.trim()) {
            this.showWarn('Department name is required');
            return;
        }
        if (!this.editingDepartment?.id) {
            this.showError('Department ID not found — cannot update');
            return;
        }

        const payload = {
            name: this.editFormModel.name.trim(),
            description: this.editFormModel.description?.trim() || ''
        };

        this.doctorService.updateDepartment(this.editingDepartment.id, payload)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    const index = this.departments.findIndex(d => d.id === this.editingDepartment?.id);
                    if (index > -1) {
                        this.departments[index] = { ...this.departments[index], ...payload };
                    }
                    this.applyFilters();
                    this.showSuccess('Department updated successfully');
                    this.closeEditDialog();
                },
                error: (err: any) => {
                    console.error('Failed to update department', err);
                    this.showError('Failed to update department');
                }
            });
    }

    // ── DELETE ────────────────────────────────────────────────

    confirmDeleteDepartment(dept: Department): void {
        if (!dept.id) {
            this.showError('Department ID not found — cannot delete');
            return;
        }
        this.confirmationService.confirm({
            message: `Are you sure you want to delete "${dept.name}"?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => this.deleteDepartment(dept)
        });
    }

    deleteDepartment(dept: Department): void {
        if (!dept.id) {
            this.showError('Department ID not found');
            return;
        }

        this.doctorService.deleteDepartment(dept.id)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    this.departments = this.departments.filter(d => d.id !== dept.id);
                    this.applyFilters();
                    this.showSuccess(`"${dept.name}" deleted`);
                },
                error: (err: any) => {
                    console.error('Failed to delete department', err);
                    this.showError('Failed to delete department');
                }
            });
    }

    // ── HELPERS ───────────────────────────────────────────────

    private resolveHospitalId(): string {
        // 1. Try from user object
        const user = this.authService.getCurrentUser();
        const fromUser = (user as any)?.hospital_id || (user as any)?.hospitalId || '';
        if (fromUser) return fromUser;

        // 2. Try from JWT
        try {
            const token = localStorage.getItem('pulseq_token');
            if (!token) return '';
            const parts = token.split('.');
            if (parts.length !== 3) return '';
            const decoded = JSON.parse(atob(parts[1]));
            console.log('[DEBUG] JWT decoded:', decoded);
            return decoded.hospital_id || decoded.hospitalId || '';
        } catch (e) {
            console.error('[DEBUG] Error decoding JWT:', e);
            return '';
        }
    }

    private showSuccess(detail: string): void {
        this.messageService.add({ severity: 'success', summary: 'Success', detail, life: 3000 });
    }

    private showError(detail: string): void {
        this.messageService.add({ severity: 'error', summary: 'Error', detail, life: 3000 });
    }

    private showWarn(detail: string): void {
        this.messageService.add({ severity: 'warn', summary: 'Warning', detail, life: 3000 });
    }
}