import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { Router } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
// PRIMENG
import { ButtonModule } from 'primeng/button';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { InputTextModule } from 'primeng/inputtext';
import { CardModule } from 'primeng/card';
// SERVICE
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { QueueService } from '../../../core/services/queue.service';
import { UserProfileService, UserProfile } from '../../../core/services/user-profile.service';
import { TokenService } from '../../../core/services/token.service';
import { NotificationService } from '../../../core/services/notification.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Doctor } from '../../../shared/models/doctor.model';
import { HospitalService } from '../../../core/services/hospital.service';

interface Hospital {
    id: string;
    name: string;
}

interface Department {
    id: string;
    name: string;
    label: string;
}

function pakistaniPhoneValidator(control: AbstractControl): ValidationErrors | null {
    if (!control.value) return null;
    const phone = control.value.trim();
    const pakistaniPhoneRegex = /^(\+92|0)?[3-4]\d{9,10}$/;
    if (pakistaniPhoneRegex.test(phone.replace(/[\s-]/g, ''))) return null;
    return { invalidPakistaniPhone: true };
}

@Component({
    selector: 'app-new-token',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        ButtonModule,
        DropdownModule,
        InputTextareaModule,
        InputTextModule,
        CardModule,
        ToastModule,
        PatientHeaderComponent
    ],
    providers: [MessageService],
    templateUrl: './new-token.component.html',
    styleUrls: ['./new-token.component.css']
})
export class NewTokenComponent implements OnInit, OnDestroy {

    tokenForm!: FormGroup;
    step: number = 1;
    userProfile: UserProfile | null = null;
    private destroy$ = new Subject<void>();

    hospitals: Hospital[] = [];
    departments: Department[] = [];
    doctors: Doctor[] = [];
    filteredDoctors: Doctor[] = [];

    assignAnyDoctor: boolean = false;
    showSkippedTokenDialog = false;
    showActiveTokenDialog = false;
    pendingDoctorSelection: Doctor | null = null;
    existingSkippedTokenId: string | null = null;
    cancellingSkippedToken = false;

    loadingDoctors: boolean = false;

    selectedHospital: Hospital | null = null;
    selectedDepartment: Department | null = null;
    selectedDoctor: Doctor | null = null;

    constructor(
        private fb: FormBuilder,
        private router: Router,
        private messageService: MessageService,
        private queueService: QueueService,
        private userProfileService: UserProfileService,
        private hospitalService: HospitalService,
        private tokenService: TokenService,
        private notificationService: NotificationService
    ) { }

    ngOnInit(): void {
        this.tokenForm = this.fb.group({
            hospital: [null, Validators.required],
            department: [null, Validators.required],
            doctor: [null],
            patientName: ['', Validators.required],
            phone: ['', [Validators.required, pakistaniPhoneValidator]],
            age: [null],
            gender: ['Male'],
            specialNotes: [''],
            reason: ['', [Validators.required, Validators.minLength(5)]]
        });

        this.userProfileService.profile$.pipe(takeUntil(this.destroy$))
            .subscribe(profile => {
                this.userProfile = profile;
            });

        this.hospitalService.listHospitals(50, 1).subscribe({
            next: (res: any) => {
                if (res && res.data) {
                    this.hospitals = res.data.map((h: any) => ({
                        id: h.id,
                        name: h.name
                    }));
                }
            },
            error: (err) => {
                console.error('Failed to load hospitals:', err);
                this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load hospitals' });
            }
        });
    }

    confirmRemoveSkippedAndBook(): void {
        if (!this.existingSkippedTokenId || !this.pendingDoctorSelection) return;
        this.cancellingSkippedToken = true;

        this.tokenService.cancelToken(this.existingSkippedTokenId, { reason: 'Patient requested rebooking' }).subscribe({
            next: () => {
                this.cancellingSkippedToken = false;
                this.showSkippedTokenDialog = false;
                this.selectedDoctor = this.pendingDoctorSelection;
                this.tokenForm.get('doctor')?.setValue(this.pendingDoctorSelection);
                this.pendingDoctorSelection = null;
                this.existingSkippedTokenId = null;
                this.step = 4;
            },
            error: () => {
                this.cancellingSkippedToken = false;
                this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Could not remove skipped token. Please try again.', life: 3500 });
            }
        });
    }

    cancelSkippedDialog(): void {
        this.showSkippedTokenDialog = false;
        this.pendingDoctorSelection = null;
        this.existingSkippedTokenId = null;
    }

    closeActiveTokenDialog(): void {
        this.showActiveTokenDialog = false;
        this.pendingDoctorSelection = null;
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    selectHospital(h: Hospital): void {
        this.selectedHospital = h;
        this.tokenForm.get('hospital')?.setValue(h);

        this.hospitalService.getHospitalDepartments(h.id).subscribe({
            next: (catRes: any) => {
                const depts: Department[] = [];
                if (catRes && catRes.data) {
                    catRes.data.forEach((dept: any) => {
                        if (typeof dept === 'string') {
                            depts.push({ id: dept, name: dept, label: dept });
                        } else {
                            depts.push({ id: dept.id, name: dept.name, label: dept.name });
                        }
                    });
                }
                this.departments = depts;
                if (this.departments.length === 0) {
                    this.messageService.add({ severity: 'info', summary: 'No Departments', detail: 'No departments configured for this hospital.' });
                }
                this.step = 2;
            },
            error: (err) => {
                console.error('Failed to load departments:', err);
                this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load departments' });
            }
        });
    }

    selectDepartment(d: Department): void {
        this.selectedDepartment = d;
        this.tokenForm.get('department')?.setValue(d);
        this.selectedDoctor = null;
        this.filteredDoctors = [];
        this.tokenForm.get('doctor')?.reset();
        this.assignAnyDoctor = false;
        this.loadingDoctors = true;
        this.step = 3;

        this.hospitalService.getHospitalDoctorsBySubcategory(this.selectedHospital!.id, d.name, 50).subscribe({
            next: (res: any) => {
                const apiDoctors = res.doctors || res.data || [];
                this.filteredDoctors = apiDoctors.map((doc: any) => ({
                    id: doc.id,
                    name: doc.name || `${doc.first_name ?? ''} ${doc.last_name ?? ''}`.trim(),
                    department: doc.department || doc.specialization || d.name,
                    specialization: doc.specialization || doc.department || d.name,
                    qualifications: doc.qualifications || doc.qualification || '',
                    timings: doc.timings || doc.working_hours || 'Available',
                    available: doc.status === 'active' || doc.status === 'available' || !doc.status,
                    fee: doc.consultation_fee ? `Rs. ${doc.consultation_fee}` : 'Free',
                    onLeave: doc.status === 'on_leave'
                }));
                this.loadingDoctors = false;
                if (this.filteredDoctors.length === 0) {
                    this.messageService.add({ severity: 'info', summary: 'No Doctors', detail: `No doctors found for ${d.label}` });
                }
            },
            error: (err) => {
                console.error('Failed to load doctors for department:', err);
                this.loadingDoctors = false;
                this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load doctors for this department' });
            }
        });
    }

    // ─── FIXED: Unavailable doctors are now fully blocked ───────────────────────
    selectDoctor(d: Doctor): void {
        // Block doctors on leave — cannot be booked at all
        if (d.onLeave) {
            this.messageService.add({
                severity: 'warn',
                summary: 'Doctor On Leave',
                detail: `${d.name} is currently on leave and cannot be booked.`,
                life: 3500
            });
            return; // stop here, do not proceed
        }

        // Block unavailable doctors — show error and stop
        if (!d.available) {
            this.messageService.add({
                severity: 'error',
                summary: 'Doctor Unavailable',
                detail: `${d.name} is currently unavailable and cannot be booked at this time.`,
                life: 3500
            });
            return; // stop here, do not proceed to next step
        }

        // Doctor is available — check for existing tokens
        this.tokenService.getMyTokens(false).subscribe({
            next: (res: any) => {
                const tokens: any[] = Array.isArray(res?.data) ? res.data : [];
                const existingToken = tokens.find(t => t.doctor_id === d.id);

                if (existingToken) {
                    this.pendingDoctorSelection = d;

                    if (existingToken.status === 'skipped') {
                        this.existingSkippedTokenId = existingToken.id;
                        this.showSkippedTokenDialog = true;
                    } else {
                        this.showActiveTokenDialog = true;
                    }
                } else {
                    this.selectedDoctor = d;
                    this.tokenForm.get('doctor')?.setValue(d);
                    this.step = 4;
                }
            },
            error: () => {
                // On error fetching tokens, still allow booking
                this.selectedDoctor = d;
                this.tokenForm.get('doctor')?.setValue(d);
                this.step = 4;
            }
        });
    }
    // ────────────────────────────────────────────────────────────────────────────

    previousStep(): void {
        if (this.step === 2) this.step = 1;
        else if (this.step === 3) this.step = 2;
        else if (this.step === 4) this.step = 3;
    }

    getDoctorCountForDepartment(dept: Department): number { return 0; }

    get f() { return this.tokenForm.controls; }

    toggleAssignAnyDoctor(): void {
        this.assignAnyDoctor = !this.assignAnyDoctor;
        const availableDoctors = this.filteredDoctors.filter(d => d.available && !d.onLeave);
        if (this.assignAnyDoctor) {
            if (availableDoctors.length > 0) {
                const random = availableDoctors[Math.floor(Math.random() * availableDoctors.length)];
                this.tokenForm.get('doctor')?.setValue(random);
                this.selectedDoctor = random;
            } else {
                this.tokenForm.get('doctor')?.reset();
                this.selectedDoctor = null;
            }
            this.tokenForm.get('doctor')?.disable();
            this.step = 4;
        } else {
            this.tokenForm.get('doctor')?.reset();
            this.selectedDoctor = null;
            this.tokenForm.get('doctor')?.enable();
        }
    }

    submitForm(): void {
        if (this.tokenForm.invalid) {
            this.tokenForm.markAllAsTouched();
            return;
        }

        const value = this.tokenForm.getRawValue();
        console.log('Submitting token with:', {
            patient_name: value.patientName,
            patient_phone: value.phone,
            patient_age: value.age,
            patient_gender: value.gender
        });

        const requestData = {
            doctor_id: value.doctor?.id || '',
            hospital_id: value.hospital?.id || '',
            reason_for_visit: value.reason,
            patient_name: value.patientName,
            patient_phone: value.phone,
            patient_age: value.age || null,
            patient_gender: value.gender || null,
            special_notes: value.specialNotes || null
        };

        this.tokenService.generateTokenWithDetails(requestData).subscribe({
            next: (res: any) => {
                const created = res?.data?.token || res?.data || res?.token || res;
                const tokenNo = created?.display_code || created?.token_number?.toString() || 'Success';
                this.messageService.add({
                    severity: 'success',
                    summary: 'Token Generated',
                    detail: `Your token ${tokenNo} has been successfully created.`,
                    life: 4000
                });
                this.notificationService.sendTokenCreated(tokenNo);
                setTimeout(() => { this.router.navigate(['/my-token']); }, 2000);
            },
            error: (err) => {
                console.error('Failed to generate token:', err);

                let errorDetail = 'Failed to generate token. Please try again.';

                if (err?.error?.message) {
                    errorDetail = err.error.message;
                } else if (err?.error?.detail) {
                    errorDetail = err.error.detail;
                } else if (err?.error?.data?.detail) {
                    errorDetail = err.error.data.detail;
                }

                if (errorDetail.toLowerCase().includes('active appointment')) {
                    errorDetail += ' You can generate a new token again once your consultation is completed.';
                }

                this.messageService.add({
                    severity: 'error',
                    summary: 'Cannot Generate Token',
                    detail: errorDetail,
                    life: 5000
                });
            }
        });
    }

    cancelForm(): void { this.router.navigate(['/dashboard']); }
    openNotifications(): void { this.router.navigate(['/notifications']); }
    nextStep(): void { if (this.step < 4) this.step++; }
}