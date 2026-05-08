import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
// PRIMENG
import { ButtonModule } from 'primeng/button';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { InputTextModule } from 'primeng/inputtext';
import { CardModule } from 'primeng/card';
// SERVICE
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Doctor } from '../../shared/models/doctor.model';

interface Hospital {
    id: string;
    name: string;
}

interface Department {
    id: string;
    name: string;
    label: string;
}

// Custom validator for Pakistani phone numbers
function pakistaniPhoneValidator(control: AbstractControl): ValidationErrors | null {
    if (!control.value) return null;
    const phone = control.value.trim();
    const pakistaniPhoneRegex = /^(\+92|0)?[3-4]\d{9,10}$/;
    if (pakistaniPhoneRegex.test(phone.replace(/[\s-]/g, ''))) return null;
    return { invalidPakistaniPhone: true };
}

@Component({
    selector: 'app-demo-booking',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        RouterModule,
        ButtonModule,
        DropdownModule,
        InputTextareaModule,
        InputTextModule,
        CardModule,
        ToastModule
    ],
    providers: [MessageService],
    templateUrl: './demo-booking.component.html',
    styleUrls: ['./demo-booking.component.css']
})
export class DemoBookingComponent implements OnInit, OnDestroy {

    tokenForm!: FormGroup;
    step = 1;
    private destroy$ = new Subject<void>();

    hospitals: Hospital[] = [];
    departments: Department[] = [];
    doctors: Doctor[] = [];

    filteredDoctors: Doctor[] = [];
    assignAnyDoctor = false;

    selectedHospital: Hospital | null = null;
    selectedDepartment: Department | null = null;
    selectedDoctor: Doctor | null = null;

    constructor(
        private fb: FormBuilder,
        private router: Router,
        private messageService: MessageService
    ) { }

    ngOnInit(): void {

        this.hospitals = [
            { id: 'h1', name: 'City Hospital' },
            { id: 'h2', name: 'General Care Clinic' }
        ];

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
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── STEP NAVIGATION ──

    selectHospital(h: Hospital): void {
        this.selectedHospital = h;
        this.tokenForm.get('hospital')?.setValue(h);
        
        // Hardcoded Departments
        this.departments = [
            { id: 'd1', name: 'Cardiology', label: 'Cardiology' },
            { id: 'd2', name: 'General Medicine', label: 'General Medicine' },
            { id: 'd3', name: 'Pediatrics', label: 'Pediatrics' }
        ];
        this.step = 2;

        // Hardcoded Doctors
        this.doctors = [
            { id: 'doc1', name: 'Dr. Sarah Khan', department: 'Cardiology', specialization: 'Cardiology', qualifications: 'MBBS, MD', timings: 'Available', available: true, fee: 'Rs. 1500', onLeave: false },
            { id: 'doc2', name: 'Dr. Asim Ahmed', department: 'General Medicine', specialization: 'General Medicine', qualifications: 'MBBS', timings: 'Available', available: true, fee: 'Rs. 1000', onLeave: false },
            { id: 'doc3', name: 'Dr. Fatima Ali', department: 'Pediatrics', specialization: 'Pediatrics', qualifications: 'MBBS, FCPS', timings: 'Available', available: true, fee: 'Rs. 1200', onLeave: false }
        ];
    }

    selectDepartment(d: Department): void {
        this.selectedDepartment = d;
        this.tokenForm.get('department')?.setValue(d);
        this.filteredDoctors = this.doctors.filter(doc => doc.specialization === d.name || doc.department === d.name);
        this.selectedDoctor = null;
        this.tokenForm.get('doctor')?.reset();
        this.assignAnyDoctor = false;
        this.step = 3;
    }

    selectDoctor(d: Doctor): void {
        // Block on-leave doctors entirely
        if (d.onLeave) {
            this.messageService.add({
                severity: 'warn',
                summary: 'Doctor On Leave',
                detail: `${d.name} is currently on leave and cannot be booked.`,
                life: 3500
            });
            return;
        }
        // Warn but still allow booking unavailable doctors (advance booking)
        if (!d.available) {
            this.messageService.add({
                severity: 'info',
                summary: 'Doctor Unavailable',
                detail: `${d.name} is currently unavailable. You can still book in advance.`,
                life: 3500
            });
        }
        this.selectedDoctor = d;
        this.tokenForm.get('doctor')?.setValue(d);
        this.step = 4;
    }

    previousStep(): void {
        if (this.step === 2) this.step = 1;
        else if (this.step === 3) this.step = 2;
        else if (this.step === 4) this.step = 3;
    }

    getDoctorCountForDepartment(dept: Department): number {
        return this.doctors.filter(
            doc => doc.specialization === dept.name && doc.available && !doc.onLeave
        ).length;
    }

    get f() { return this.tokenForm.controls; }

    // ── ASSIGN ANY DOCTOR ──
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

    // ── SUBMIT ──
    submitForm(): void {
        if (this.tokenForm.invalid) {
            this.tokenForm.markAllAsTouched();
            return;
        }

        // Show success step instead of hitting backend
        this.step = 5;
    }

    cancelForm(): void { this.router.navigate(['/']); }
    openNotifications(): void { }
    nextStep(): void { if (this.step < 4) this.step++; }
}