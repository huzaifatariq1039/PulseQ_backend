import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ToastModule } from 'primeng/toast';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TooltipModule } from 'primeng/tooltip';
import { DropdownModule } from 'primeng/dropdown';
import { MessageService, ConfirmationService } from 'primeng/api';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { QueueService } from '../../../core/services/queue.service';
import { DoctorService } from '../../../core/services/doctor.service';
import { ReceptionService } from '../../../core/services/reception.service';
import { AuthService } from '../../../core/services/auth.service';
import { Token } from '../../../shared/models/token.model';
import { Doctor } from '../../../shared/models/doctor.model';
import { ReceptionSidebarComponent } from '../shared/components/reception-sidebar/reception-sidebar.component';
import { NotificationService } from '../../../core/services/notification.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface Patient {
    id?: string;
    token: string;
    name: string;
    age?: number;
    gender?: string;
    reason: string;
    status?: 'pending' | 'completed' | 'skipped';
    department?: string;
    phone?: string;
    paymentStatus?: 'paid' | 'unpaid';
    mrn?: string;
    doctorId?: string;
    doctorName?: string;
}

@Component({
    selector: 'app-reception-queue',
    standalone: true,
    imports: [
        CommonModule, FormsModule, TableModule, ButtonModule, CardModule,
        ToastModule, DialogModule, InputTextModule, TooltipModule,
        DropdownModule, ConfirmDialogModule, ReceptionSidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './reception-queue.component.html',
    styleUrls: ['./reception-queue.component.css']
})
export class ReceptionQueueComponent implements OnInit, OnDestroy {

    statuses = [
        { label: 'Status', value: null, disabled: true },
        { label: 'All', value: null },
        { label: 'Pending', value: 'pending' },
        { label: 'Completed', value: 'completed' },
        { label: 'Skipped', value: 'skipped' }
    ];

    genderOptions = [
        { label: 'Male', value: 'Male' },
        { label: 'Female', value: 'Female' },
        { label: 'Other', value: 'Other' }
    ];

    departments: { label: string; value: string }[] = [];

    paymentOptions = [
        { label: 'Payment', value: null, disabled: true },
        { label: 'All', value: null },
        { label: 'Paid', value: 'paid' },
        { label: 'Unpaid', value: 'unpaid' }
    ];
    paymentFilter: string | null = null;

    get paymentOptionsNoAll() {
        return this.paymentOptions.filter(o => o.value !== null);
    }

    tokens: Patient[] = [];
    filteredTokens: Patient[] = [];
    availableDoctors: Doctor[] = [];
    private destroy$ = new Subject<void>();
    selectedStatus: string | null = null;
    searchText = '';
    editVisible = false;
    viewVisible = false;
    deleteConfirmVisible = false;
    editModel: Partial<Patient> | null = null;
    viewModel: Patient | null = null;
    deleteModel: Patient | null = null;
    currentNav: 'dashboard' | 'queue' | 'manage-doctors' = 'queue';
    sidebarOpen = false;

    private allDoctorsCache: Doctor[] = [];

    constructor(
        private messageService: MessageService,
        private router: Router,
        private confirmationService: ConfirmationService,
        private queueService: QueueService,
        private doctorService: DoctorService,
        private receptionService: ReceptionService,
        private authService: AuthService,
        private notificationService: NotificationService
    ) { }

    ngOnInit() {
        this.doctorService.getDoctorsObservable().subscribe(docs => {
            this.allDoctorsCache = docs;
        });
        this.loadQueue();
        this.loadDepartments();
        this.doctorService.doctors$
            .pipe(takeUntil(this.destroy$))
            .subscribe(doctors => {
                this.availableDoctors = doctors.filter(d => d.available);
            });
    }

    private getHospitalId(): string {
        const user: any = this.authService.getCurrentUser();
        return user?.hospitalId || user?.hospital_id || '';
    }

    private loadDepartments(): void {
        const hospitalId = this.getHospitalId();
        this.doctorService.listDepartments(hospitalId)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    const raw: any[] = res?.data || res || [];
                    this.departments = raw.map(d => ({
                        label: d.name || d.label || d,
                        value: d.name || d.value || d
                    }));
                },
                error: () => {
                    this.departments = [{ label: 'General Medicine', value: 'General Medicine' }];
                }
            });
    }

    /**
     * Safely parse age from any input type.
     * Handles strings like "44y", numbers, null, undefined.
     * Always returns a clean integer with no off-by-one drift.
     */
    private parseAge(raw: any): number {
        if (raw === null || raw === undefined || raw === '') return 0;
        let str = raw.toString().trim();
        str = str.replace(/^(age|patient|p|age-|patient_)?[-_]*/i, '');
        const cleaned = str.replace(/[^0-9]/g, '');
        const parsed = parseInt(cleaned, 10);
        return isNaN(parsed) || parsed < 0 ? 0 : Math.min(parsed, 150);
    }

    /** Map any backend status string to local union type */
    private mapStatus(raw: string): 'pending' | 'completed' | 'skipped' {
        const s = (raw || '').toLowerCase();
        if (s === 'done' || s === 'completed') return 'completed';
        if (s === 'skipped') return 'skipped';
        return 'pending';
    }

    loadQueue(): void {
        this.receptionService.getQueue(this.getHospitalId())
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (res: any) => {
                    const rawTokens = res?.data || res?.queue || res || [];
                    const tokens = Array.isArray(rawTokens) ? rawTokens : [];
                    this.tokens = tokens.map((t: any) => {
                        let doctorName = '';
                        if (t.doctor_id || t.doctorId) {
                            const dId = t.doctor_id || t.doctorId;
                            let doc = this.availableDoctors.find(d => d.id === dId);
                            if (!doc && this.allDoctorsCache.length) {
                                doc = this.allDoctorsCache.find(d => d.id === dId);
                            }
                            doctorName = doc ? doc.name : (t.doctor_name || t.doctorName || 'Any');
                        } else {
                            doctorName = t.doctor_name || t.doctorName || '';
                        }

                        return {
                            id: t.token_id || t.id || t.tokenId || '',
                            token: t.token_number || t.tokenNumber || t.token || 'T-00',
                            name: t.patient_name || t.patientName || t.patientId || 'Unknown',
                            age: this.parseAge(t.patient_age ?? t.patientAge ?? t.age),
                            gender: t.patient_gender || t.patientGender || t.gender || 'Unknown',
                            reason: t.reason || t.reason_for_visit || t.reasonForVisit || '',
                            status: this.mapStatus(t.status || t.state || ''),
                            department: t.department || 'General Medicine',
                            phone: t.patient_phone || t.phone || t.patientPhone || '',
                            paymentStatus: t.payment_status || t.paymentStatus || 'unpaid',
                            mrn: t.mrn || t.patient_id || '-',
                            doctorId: t.doctor_id || t.doctorId,
                            doctorName
                        };
                    });
                    this.filter();
                },
                error: (err) => {
                    console.error('Failed to load queue from API', err);
                    // Fallback to local queue service on API failure
                    this.queueService.getQueue()
                        .pipe(takeUntil(this.destroy$))
                        .subscribe(tokens => {
                            this.tokens = tokens.map((t: Token) => {
                                let doctorName = '';
                                if (t.doctorId) {
                                    let doc = this.availableDoctors.find(d => d.id === t.doctorId);
                                    if (!doc && this.allDoctorsCache.length) {
                                        doc = this.allDoctorsCache.find(d => d.id === t.doctorId);
                                    }
                                    doctorName = doc ? doc.name : '';
                                }
                                return {
                                    token: t.tokenNumber,
                                    name: t.patientName || t.patientId,
                                    age: this.parseAge(t.patientAge),
                                    gender: (t.patientGender as any) || 'Unknown',
                                    reason: (t.reasonForVisit as any) || '',
                                    status: this.mapStatus(t.status || ''),
                                    department: t.department,
                                    phone: t.patientPhone,
                                    paymentStatus: (t as any).paymentStatus || 'unpaid',
                                    mrn: (t as any).mrn || (t as any).patient_id || '-',
                                    doctorId: t.doctorId,
                                    doctorName
                                };
                            });
                            this.filter();
                        });
                }
            });
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    filter() {
        // Separate skipped and non-skipped patients
        const skipped = this.tokens.filter(t => t.status === 'skipped');
        let nonSkipped = this.tokens.filter(t => t.status !== 'skipped');

        // Apply status filter only to non-skipped patients
        if (this.selectedStatus && this.selectedStatus !== 'skipped') {
            nonSkipped = nonSkipped.filter(t => t.status === this.selectedStatus);
        } else if (this.selectedStatus === 'skipped') {
            // If user explicitly selects 'Skipped' status, show only skipped
            this.filteredTokens = skipped;
            return;
        }

        // Apply payment filter
        if (this.paymentFilter) {
            nonSkipped = nonSkipped.filter(t => (t.paymentStatus || 'unpaid') === this.paymentFilter);
        }

        // Apply search filter
        if (this.searchText) {
            nonSkipped = nonSkipped.filter(t =>
                t.name.toLowerCase().includes(this.searchText.toLowerCase()) ||
                t.token.toLowerCase().includes(this.searchText.toLowerCase())
            );
            // Also apply search to skipped patients
            const filteredSkipped = skipped.filter(t =>
                t.name.toLowerCase().includes(this.searchText.toLowerCase()) ||
                t.token.toLowerCase().includes(this.searchText.toLowerCase())
            );
            // Skipped patients always appear at the top
            this.filteredTokens = [...filteredSkipped, ...nonSkipped];
        } else {
            // Skipped patients always appear at the top regardless of other filters
            this.filteredTokens = [...skipped, ...nonSkipped];
        }
    }

    onPaymentChange() { this.filter(); }
    onStatusChange() { this.filter(); }
    onSearchChange(text: string) { this.searchText = text; this.filter(); }
    save() { this.messageService.add({ severity: 'success', summary: 'Saved', detail: 'Queue saved (in-memory)' }); }

    view(row: Patient) { this.viewModel = row; this.viewVisible = true; }

    edit(row: Patient) {
        this.editModel = {
            ...row,
            age: this.parseAge(row.age)
        };
        this.editVisible = true;
    }

    onAgeChange(value: any): void {
        if (this.editModel) {
            this.editModel.age = this.parseAge(value);
        }
    }

    saveEdit() {
        if (!this.editModel) return;
        const idx = this.tokens.findIndex(t => t.token === this.editModel!.token);
        if (idx < 0) return;

        const mapped = { ...this.tokens[idx], ...(this.editModel as Patient) };
        if (!mapped.id) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Token ID not found' });
            this.editVisible = false;
            return;
        }

        const safeAge = this.parseAge(this.editModel.age);

        const updated: any = {
            patient_name: mapped.name,
            patient_age: safeAge,
            patient_gender: mapped.gender,
            department: mapped.department,
            payment_status: mapped.paymentStatus || 'unpaid',
            reason: mapped.reason,
        };

        // Use patient_phone as the backend canonical field name
        if (mapped.phone) {
            updated.patient_phone = mapped.phone;
        }

        this.receptionService.updateToken(mapped.id, updated)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    this.tokens[idx] = {
                        ...this.tokens[idx],
                        ...(this.editModel as Patient),
                        age: safeAge
                    };
                    this.filter();
                    this.messageService.add({ severity: 'success', summary: 'Updated', detail: `${mapped.token} saved successfully` });
                    setTimeout(() => this.loadQueue(), 800);
                },
                error: () => {
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update token' });
                }
            });
        this.editVisible = false;
    }

    delete(row: Patient) { this.deleteModel = row; this.deleteConfirmVisible = true; }

    confirmDelete() {
        if (!this.deleteModel) return;
        if (!this.deleteModel.id) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Token ID not found' });
            this.deleteConfirmVisible = false;
            return;
        }

        const tokenId = this.deleteModel.id;
        const tokenToDelete = this.deleteModel;
        const tokenIndex = this.filteredTokens.findIndex(t => t.id === tokenId);

        if (tokenIndex > -1) {
            this.filteredTokens.splice(tokenIndex, 1);
        }

        this.receptionService.deleteToken(tokenId)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `${tokenToDelete.token} removed from queue`, life: 3000 });
                    this.loadQueue();
                },
                error: (err) => {
                    console.error('Failed to delete token:', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete token' });
                    this.loadQueue();
                }
            });
        this.deleteConfirmVisible = false;
    }

    skipToken(row: Patient): void {
        if (!row.id) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Token ID not found, cannot skip.', life: 3000 });
            return;
        }

        this.receptionService.skipToken(row.id)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    this.messageService.add({ severity: 'warn', summary: 'Skipped', detail: `${row.token} has been skipped`, life: 3000 });
                    this.notificationService.sendTokenSkipped(row.token, 'reception');

                    // Optimistic update — mark token as skipped locally immediately
                    // so the Re-add button renders before the reload completes.
                    // This compensates for the backend not returning skipped status
                    // in the queue response yet.
                    const idx = this.tokens.findIndex(t => t.id === row.id);
                    if (idx !== -1) {
                        this.tokens[idx] = { ...this.tokens[idx], status: 'skipped' };
                        this.filter();
                    }

                    setTimeout(() => this.loadQueue(), 500);
                },
                error: (err) => {
                    console.error('Failed to skip token:', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.message || 'Failed to skip token', life: 3000 });
                }
            });
    }

    // Accepts Partial<Patient> so it works from both table row and edit dialog
    reAddToken(row: Partial<Patient>) {
        if (!row.id) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Patient ID not found', life: 3000 });
            return;
        }

        this.receptionService.reAddToken(row.id)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (response: any) => {
                    const updatedStatus = response?.data?.status;
                    if (updatedStatus && updatedStatus.toLowerCase() !== 'skipped') {
                        const arr3 = this.queueService.getQueueSnapshot();
                        const found3 = arr3.find(x => x.tokenNumber === row.token);
                        if (found3) this.queueService.updateTokenStatus(found3.id, 'WAITING');
                        this.messageService.add({ severity: 'success', summary: 'Re-added', detail: `${row.token} added back to queue`, life: 3000 });
                    } else {
                        console.error('Backend did not update token status. Response:', response?.data);
                        this.messageService.add({
                            severity: 'error',
                            summary: 'Backend Error',
                            detail: `Failed to update token status. Status still: ${updatedStatus}. Contact admin.`,
                            life: 5000
                        });
                    }
                    setTimeout(() => this.loadQueue(), 500);
                },
                error: (err) => {
                    console.error('Failed to re-add token:', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to re-add patient to queue', life: 3000 });
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

    toggleSidebar(): void { this.sidebarOpen = !this.sidebarOpen; }

    downloadSlip(row: Patient) {
        this.messageService.add({ severity: 'info', summary: 'Downloading', detail: 'Generating slip...', life: 2000 });
        setTimeout(() => {
            const canvas = document.createElement('canvas');
            canvas.width = 500; canvas.height = 600;
            const ctx = canvas.getContext('2d');
            if (ctx) {
                ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#2563eb'; ctx.fillRect(0, 0, canvas.width, 8);
                ctx.fillStyle = '#000000'; ctx.font = 'bold 72px Arial'; ctx.textAlign = 'center';
                ctx.fillText(row.token || '', canvas.width / 2, 120);
                ctx.font = '14px Arial'; ctx.fillStyle = '#666666'; ctx.textAlign = 'center';
                let yPos = 170; const lineHeight = 22;
                ctx.fillText(`Hospital: PulseQ Hospital`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Department: ${row.department || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Doctor: ${row.doctorName || 'Any'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Name: ${row.name || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Phone: ${row.phone || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`MRN: ${row.mrn || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Age: ${row.age ?? '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Gender: ${row.gender || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Payment: ${(row.paymentStatus || 'unpaid').toUpperCase()}`, canvas.width / 2, yPos); yPos += lineHeight;
                ctx.fillText(`Status: ${(row.status || 'pending').toUpperCase()}`, canvas.width / 2, yPos);
            }
            canvas.toBlob((blob) => {
                if (blob) {
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url; link.download = `ticket-${row.token}.png`; link.click();
                    URL.revokeObjectURL(url);
                    this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Slip downloaded successfully', life: 3000 });
                }
            });
        }, 1500);
    }

    signOut() { this.router.navigate(['/']); }
}