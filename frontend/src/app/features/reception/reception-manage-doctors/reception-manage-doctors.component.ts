import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ToastModule } from 'primeng/toast';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { CheckboxModule } from 'primeng/checkbox';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { ReceptionSidebarComponent } from '../shared/components/reception-sidebar/reception-sidebar.component';
import { DoctorService } from '../../../core/services/doctor.service';
import { ReceptionService } from '../../../core/services/reception.service';
import { Doctor } from '../../../shared/models/doctor.model';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
    selector: 'app-reception-manage-doctors',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        TableModule,
        ButtonModule,
        CardModule,
        ToastModule,
        DialogModule,
        InputTextModule,
        DropdownModule,
        CheckboxModule,
        TooltipModule,
        ReceptionSidebarComponent
    ],
    providers: [MessageService],
    templateUrl: './reception-manage-doctors.component.html',
    styleUrls: ['./reception-manage-doctors.component.css']
})
export class ReceptionManageDoctorsComponent implements OnInit, OnDestroy {
    editStatus: 'available' | 'unavailable' | 'onLeave' = 'available';
    editFee: number | null = null;

    // Separate start/end time fields for editing
    editStartTime: string = '';
    editEndTime: string = '';

    doctors: Doctor[] = [];
    filteredDoctors: Doctor[] = [];
    searchText = '';
    selectedDepartment: string | null = null;
    departments: { label: string; value: string }[] = [];

    currentNav: 'dashboard' | 'queue' | 'manage-doctors' = 'manage-doctors';
    sidebarOpen = false;
    editVisible = false;
    editModel: Partial<Doctor> | null = null;

    private destroy$ = new Subject<void>();

    constructor(
        private router: Router,
        private messageService: MessageService,
        private doctorService: DoctorService,
        private receptionService: ReceptionService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit() {
        this.loadDepartments();
        this.loadDoctors();
    }

    ngOnDestroy() {
        this.destroy$.next();
        this.destroy$.complete();
    }

    loadDepartments() {
        this.doctorService.listDepartments().pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                const depts = res?.data || res || [];
                this.departments = Array.isArray(depts)
                    ? depts.map((d: any) => ({ label: d.name, value: d.name }))
                    : [];
                this.cdr.markForCheck();
            },
            error: (err) => console.error('Failed to load departments', err)
        });
    }
    loadDoctors() {
        this.doctorService.manageDoctors({
            search: this.searchText,
            department: this.selectedDepartment || undefined
        }).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                const docs = res?.data || res?.doctors || res || [];
                this.doctors = Array.isArray(docs) ? docs.map((d: any) => ({
                    id: d.id || d.doctor_id,
                    name: d.name,
                    specialization: d.specialization || d.department,
                    qualifications: d.qualifications || '',
                    timings: d.timings || `${d.start_time || ''} - ${d.end_time || ''}`,
                    available: d.status === 'available',
                    onLeave: d.status === 'on_leave',
                    fee: `Rs. ${d.consultation_fee ?? d.fee ?? 0}`,
                    consultationFee: d.consultation_fee ?? d.fee ?? 0,
                    department: d.department,
                    // Keep raw start/end for editing
                    start_time: d.start_time || '',
                    end_time: d.end_time || '',
                    status: d.status
                })) : [];

                this.filterDoctors();
                this.cdr.markForCheck();
            },
            error: (err) => {
                console.error('Failed to load doctors', err);
            }
        });
    }

    filterDoctors() {
        let results = [...this.doctors];
        if (this.searchText.trim()) {
            results = results.filter(d =>
                d.name.toLowerCase().includes(this.searchText.toLowerCase())
            );
        }
        if (this.selectedDepartment) {
            results = results.filter(d => d.department === this.selectedDepartment);
        }
        this.filteredDoctors = results;
        this.cdr.markForCheck();
    }

    getStatusClass(doctor: any): string {
        if (doctor.onLeave) return 'status-badge status-on-leave';
        if (doctor.available) return 'status-badge status-available';
        return 'status-badge status-offline';
    }

    getStatusText(doctor: any): string {
        if (doctor.onLeave) return 'On Leave';
        if (doctor.available) return 'Available';
        return 'Unavailable';
    }

    onSearchChange(text: string) {
        this.searchText = text;
        this.loadDoctors();
    }

    onDepartmentChange() {
        this.loadDoctors();
    }

    editDoctor(doctor: any) {
        this.editModel = { ...doctor };
        this.editFee = doctor.consultationFee ?? null;

        // Populate separate start/end time fields from raw API values
        this.editStartTime = doctor.start_time || '';
        this.editEndTime = doctor.end_time || '';

        if (doctor.onLeave) {
            this.editStatus = 'onLeave';
        } else if (doctor.available) {
            this.editStatus = 'available';
        } else {
            this.editStatus = 'unavailable';
        }
        this.editVisible = true;
    }

    /**
     * Converts "HH:MM" 24h string to "HH:MM AM/PM" 12h display string.
     * Used only for the timings display column.
     */
    private to12h(time: string): string {
        if (!time) return '';
        const [hStr, mStr] = time.split(':');
        let h = parseInt(hStr, 10);
        const m = mStr || '00';
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return `${h.toString().padStart(2, '0')}:${m} ${ampm}`;
    }

    saveEdit() {
        if (!this.editModel || !this.editModel.id) return;

        let newStatus = 'offline';
        if (this.editStatus === 'available') newStatus = 'available';
        else if (this.editStatus === 'onLeave') newStatus = 'on_leave';
        else newStatus = 'offline';

        // Validate time inputs
        if (!this.editStartTime || !this.editEndTime) {
            this.messageService.add({
                severity: 'warn',
                summary: 'Missing Times',
                detail: 'Please enter both start and end times.',
                life: 3000
            });
            return;
        }

        const payload: any = {
            status: newStatus,
            name: this.editModel.name,
            department: this.editModel.department,
            qualifications: this.editModel.qualifications || null,
            consultation_fee: this.editFee ?? null,
            // Send raw start_time and end_time — what the backend actually stores
            start_time: this.editStartTime,
            end_time: this.editEndTime
        };

        this.receptionService.updateDoctor(this.editModel.id, payload).subscribe({
            next: () => {
                this.editVisible = false;
                this.messageService.add({
                    severity: 'success',
                    summary: 'Success',
                    detail: 'Doctor updated successfully',
                    life: 3000
                });
                setTimeout(() => this.loadDoctors(), 500);
            },
            error: (err) => {
                console.error('Failed to update doctor', err);
                this.messageService.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: err?.error?.message || 'Failed to update doctor',
                    life: 3000
                });
            }
        });
    }

    navigateTo(page: 'dashboard' | 'queue' | 'manage-doctors') {
        this.currentNav = page;
        this.sidebarOpen = false;
        if (page === 'dashboard') this.router.navigate(['/dashboard']);
        else if (page === 'queue') this.router.navigate(['/queue']);
        else if (page === 'manage-doctors') this.router.navigate(['/manage-doctors']);
    }

    toggleSidebar() { this.sidebarOpen = !this.sidebarOpen; }
    signOut() { this.router.navigate(['/']); }
}