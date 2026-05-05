import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DoctorService } from '../../../core/services/doctor.service';
import { Doctor } from '../../../shared/models/doctor.model';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';

// PrimeNG
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { CheckboxModule } from 'primeng/checkbox';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
    selector: 'app-admin-manage-doctors',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        AdminSidebarComponent,
        TableModule,
        ButtonModule,
        DialogModule,
        InputTextModule,
        CheckboxModule,
        DropdownModule,
        ToastModule
    ],
    providers: [MessageService],
    templateUrl: './admin-manage-doctors.component.html',
    styleUrl: './admin-manage-doctors.component.css'
})
export class AdminManageDoctorsComponent implements OnInit, OnDestroy {

    // ── EDIT fields ──
    editStartTime: string = '';
    editEndTime: string = '';
    editFee: number = 0;

    // ── ADD fields ──
    showAddDialog = false;
    addStatus: 'available' | 'unavailable' | 'onLeave' = 'available';
    addStartTime: string = '09:00';
    addEndTime: string = '17:00';
    addFee: number = 0;
    addModel = {
        name: '',
        department: '',
        qualifications: '',
        email: '',
        phone: '',
        password: '',
        patients_per_day: 20
    };

    doctors: Doctor[] = [];
    filteredDoctors: Doctor[] = [];

    searchText = '';
    selectedDepartment: string | null = null;

    showEditDialog = false;
    showViewDialog = false;
    showQueueDialog = false;
    editStatus: 'available' | 'unavailable' | 'onLeave' = 'available';

    editModel: Doctor = {
        id: '', name: '', department: '', available: true,
        specialization: '', qualifications: '', timings: '', fee: ''
    };

    viewModel: any = null;
    queueModel: any = null;

    departments: { name: string; value: string | null }[] = [
        { name: 'All Departments', value: null }
    ];

    private destroy$ = new Subject<void>();

    constructor(
        private doctorService: DoctorService,
        private messageService: MessageService
    ) { }

    ngOnInit(): void {
        this.loadDoctorsFromApi();
        this.loadDepartments();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── HELPER METHODS ──

    convertTo12Hour(time24: string): string {
        if (!time24) return '09:00 AM';
        const [hours, minutes] = time24.split(':');
        const hour = parseInt(hours, 10);
        const min = minutes || '00';
        const period = hour >= 12 ? 'PM' : 'AM';
        const hour12 = hour % 12 === 0 ? 12 : hour % 12;
        return `${hour12}:${min} ${period}`;
    }

    // ── DATA LOADING ──

    loadDoctorsFromApi(): void {
        this.doctorService.manageDoctors({ pageSize: 100 }).subscribe({
            next: (res: any) => {
                const docs = res?.doctors || res?.data || res || [];
                if (Array.isArray(docs)) {
                    this.doctors = docs.map((d: any) => ({
                        id: d.id,
                        name: d.name,
                        specialization: d.department || d.specialization || '',
                        department: d.department || '',
                        qualifications: d.qualifications || '',
                        timings: `${this.convertTo12Hour(d.start_time)} – ${this.convertTo12Hour(d.end_time)}`,
                        available: d.status === 'available',
                        fee: d.consultation_fee ? `Rs. ${d.consultation_fee}` : '',
                        consultation_fee: d.consultation_fee || 0,
                        onLeave: d.status === 'on_leave',
                        phone: d.phone || '',
                        email: d.email || '',
                        rating: d.rating || 0,
                        reviewCount: d.review_count || 0,
                        status: d.status || 'offline',
                        start_time: d.start_time || '',
                        end_time: d.end_time || ''
                    }));
                    this.applyFilters();
                }
            },
            error: (err) => {
                console.error('Failed to load doctors from API, falling back to local', err);
                this.doctorService.doctors$
                    .pipe(takeUntil(this.destroy$))
                    .subscribe(doctors => {
                        this.doctors = doctors;
                        this.applyFilters();
                    });
            }
        });
    }

    loadDepartments(): void {
        this.doctorService.listDepartments().subscribe({
            next: (res: any) => {
                // API returns { success: true, data: [...] }
                const depts = res?.data || res?.departments || res || [];
                this.departments = [{ name: 'All Departments', value: null }];
                if (Array.isArray(depts)) {
                    depts.forEach((d: any) => {
                        const name = typeof d === 'string' ? d : (d.name || d.department || '');
                        if (name) this.departments.push({ name, value: name });
                    });
                }
            },
            error: (err) => {
                console.error('Failed to load departments', err);
            }
        });
    }

    // ── FILTERS ──

    onSearchChange(value: string): void {
        this.searchText = value;
        this.applyFilters();
    }

    onDepartmentChange(): void {
        this.applyFilters();
    }

    applyFilters(): void {
        let result = [...this.doctors];
        if (this.searchText?.trim()) {
            const term = this.searchText.toLowerCase();
            result = result.filter(d => d.name.toLowerCase().includes(term));
        }
        if (this.selectedDepartment) {
            result = result.filter(d => d.department === this.selectedDepartment);
        }
        this.filteredDoctors = result;
    }

    // ── VIEW DETAILS ──

    viewDoctor(doctor: Doctor): void {
        this.doctorService.getDoctorDetails(doctor.id).subscribe({
            next: (res: any) => {
                this.viewModel = res?.data || res || doctor;
                this.showViewDialog = true;
            },
            error: () => {
                this.viewModel = doctor;
                this.showViewDialog = true;
            }
        });
    }

    // ── QUEUE STATUS ──

    viewQueue(doctor: Doctor): void {
        this.doctorService.getDoctorQueueStatus(doctor.id).subscribe({
            next: (res: any) => {
                this.queueModel = { doctorName: doctor.name, ...(res?.data || res || {}) };
                this.showQueueDialog = true;
            },
            error: () => {
                this.queueModel = { doctorName: doctor.name, total_in_queue: 0, status: 'unknown' };
                this.showQueueDialog = true;
            }
        });
    }

    // ── ADD DOCTOR ──

    openAddDialog(): void {
        this.addModel = {
            name: '',
            department: '',
            qualifications: '',
            email: '',
            phone: '',
            password: '',
            patients_per_day: 20
        };
        this.addStartTime = '09:00';
        this.addEndTime = '17:00';
        this.addFee = 0;
        this.addStatus = 'available';
        this.showAddDialog = true;
    }

    saveAdd(): void {
        if (!this.addModel.name?.trim() || !this.addModel.department) {
            this.messageService.add({
                severity: 'error', summary: 'Validation Error',
                detail: 'Name and Department are required', life: 3000
            });
            return;
        }
        if (!this.addModel.password?.trim()) {
            this.messageService.add({
                severity: 'error', summary: 'Validation Error',
                detail: 'Password is required', life: 3000
            });
            return;
        }

        const apiStatus =
            this.addStatus === 'onLeave' ? 'on_leave' :
                this.addStatus === 'available' ? 'available' : 'offline';

        const hospitalId = JSON.parse(localStorage.getItem('pulseq_user') || '{}')?.hospital_id || '';

        const payload = {
            name: this.addModel.name.trim(),
            department: this.addModel.department,
            subcategory: '',
            hospital_id: hospitalId,
            email: this.addModel.email?.trim() || '',
            password: this.addModel.password.trim(),
            consultation_fee: this.addFee,
            session_fee: 1,
            start_time: this.addStartTime,
            end_time: this.addEndTime,
            available_days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
            patients_per_day: this.addModel.patients_per_day || 20,
            status: apiStatus
        };

        this.doctorService.createDoctor(payload as any).subscribe({
            next: () => {
                this.showAddDialog = false;
                this.messageService.add({
                    severity: 'success', summary: 'Doctor Added',
                    detail: `${this.addModel.name} has been registered successfully`, life: 3000
                });
                this.loadDoctorsFromApi();
            },
            error: (err) => {
                const detail = err?.error?.message || err?.error?.detail || 'Failed to add doctor. Please try again.';
                this.messageService.add({
                    severity: 'error', summary: 'Error', detail, life: 4000
                });
            }
        });
    }

    // ── EDIT ──

    openEditDialog(doctor: Doctor): void {
        this.editModel = { ...doctor };
        this.editStartTime = (doctor as any).start_time || '';
        this.editEndTime = (doctor as any).end_time || '';
        this.editFee = (doctor as any).consultation_fee || 0;

        if ((doctor as any).onLeave) this.editStatus = 'onLeave';
        else if (doctor.available) this.editStatus = 'available';
        else this.editStatus = 'unavailable';
        this.showEditDialog = true;
    }

    saveEdit(): void {
        if (!this.editModel.name?.trim() || !this.editModel.department) {
            this.messageService.add({
                severity: 'error', summary: 'Error',
                detail: 'Name and Department are required', life: 3000
            });
            return;
        }

        if (this.editStatus === 'available') {
            this.editModel.available = true;
            (this.editModel as any).onLeave = false;
        } else if (this.editStatus === 'unavailable') {
            this.editModel.available = false;
            (this.editModel as any).onLeave = false;
        } else {
            this.editModel.available = false;
            (this.editModel as any).onLeave = true;
        }

        const apiStatus = this.editStatus === 'onLeave' ? 'on_leave' :
            (this.editStatus === 'available' ? 'available' : 'offline');

        this.doctorService.updateDoctorApi(this.editModel.id, {
            name: this.editModel.name,
            department: this.editModel.department,
            status: apiStatus,
            consultation_fee: this.editFee,
            start_time: this.editStartTime,
            end_time: this.editEndTime
        }).subscribe({
            next: () => {
                this.doctorService.updateDoctorStatus({
                    doctor_id: this.editModel.id,
                    status: apiStatus,
                    start_time: this.editStartTime,
                    end_time: this.editEndTime
                }).subscribe({ error: () => { } });

                this.doctorService.updateDoctor(this.editModel);
                this.showEditDialog = false;
                this.messageService.add({
                    severity: 'success', summary: 'Success',
                    detail: 'Doctor updated successfully', life: 3000
                });
                this.loadDoctorsFromApi();
            },
            error: (err) => {
                console.error('Failed to update doctor via API', err);
                this.doctorService.updateDoctor(this.editModel);
                this.showEditDialog = false;
                this.messageService.add({
                    severity: 'success', summary: 'Updated (Offline)',
                    detail: 'Doctor updated locally', life: 3000
                });
                this.applyFilters();
            }
        });
    }

    closeDialog(): void {
        this.showEditDialog = false;
    }

    // ── DELETE ──

    deleteDoctor(id: string): void {
        this.doctorService.deleteDoctorApi(id).subscribe({
            next: () => {
                this.doctorService.deleteDoctor(id);
                this.messageService.add({
                    severity: 'success', summary: 'Deleted',
                    detail: 'Doctor deleted successfully', life: 3000
                });
                this.loadDoctorsFromApi();
            },
            error: (err) => {
                console.error('Failed to delete doctor via API', err);
                let errorDetail = 'Cannot delete doctor. Contact IT support.';
                if (err?.error?.message) {
                    errorDetail = err.error.message;
                } else if (err?.error?.detail) {
                    errorDetail = err.error.detail;
                }
                this.messageService.add({
                    severity: 'error', summary: 'Cannot Delete',
                    detail: errorDetail, life: 4000
                });
            }
        });
    }

    // ── STATUS HELPERS ──

    getStatusClass(doctor: Doctor): string {
        if ((doctor as any).onLeave) return 'status-on-leave';
        if (doctor.available) return 'status-available';
        return 'status-offline';
    }

    getStatusText(doctor: Doctor): string {
        if ((doctor as any).onLeave) return 'On Leave';
        return doctor.available ? 'Available' : 'Offline';
    }
}