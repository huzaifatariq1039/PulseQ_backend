import { Component, OnInit, OnDestroy, HostListener, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
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

export type SortField = 'token' | 'name' | 'status' | 'payment' | 'department' | 'doctor';
export type SortDir = 'asc' | 'desc';

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

    // ── Filter panel state ────────────────────────────────────────────────────
    filterPanelOpen = false;

    // Active filters
    selectedStatus: string | null = null;
    paymentFilter: string | null = null;
    selectedDoctorId: string | null = null;
    selectedDepartment: string | null = null;
    searchText = '';

    // Sort
    sortField: SortField = 'token';
    sortDir: SortDir = 'asc';

    sortOptions: { label: string; value: SortField }[] = [
        { label: 'Token', value: 'token' },
        { label: 'Name', value: 'name' },
        { label: 'Status', value: 'status' },
        { label: 'Payment', value: 'payment' },
        { label: 'Department', value: 'department' },
        { label: 'Doctor', value: 'doctor' },
    ];

    // Dropdown option lists
    statuses = [
        { label: 'All statuses', value: null },
        { label: 'Pending', value: 'pending' },
        { label: 'Completed', value: 'completed' },
        { label: 'Skipped', value: 'skipped' }
    ];

    paymentOptions = [
        { label: 'All payments', value: null },
        { label: 'Paid', value: 'paid' },
        { label: 'Unpaid', value: 'unpaid' }
    ];

    genderOptions = [
        { label: 'Male', value: 'Male' },
        { label: 'Female', value: 'Female' },
        { label: 'Other', value: 'Other' }
    ];

    departments: { label: string; value: string }[] = [];
    availableDoctors: Doctor[] = [];

    get doctorOptions(): { label: string; value: string | null }[] {
        return [
            { label: 'Any doctor', value: null },
            ...this.availableDoctors.map(d => ({ label: d.name, value: d.id }))
        ];
    }

    get departmentOptions(): { label: string; value: string | null }[] {
        return [
            { label: 'All departments', value: null },
            ...this.departments
        ];
    }

    get paymentOptionsNoAll() {
        return this.paymentOptions.filter(o => o.value !== null);
    }

    /** Count of active filters (excluding search & sort) for the badge */
    get activeFilterCount(): number {
        return [this.selectedStatus, this.paymentFilter, this.selectedDoctorId, this.selectedDepartment]
            .filter(v => v !== null && v !== undefined).length;
    }

    // ── Data ─────────────────────────────────────────────────────────────────
    tokens: Patient[] = [];
    filteredTokens: Patient[] = [];
    private allDoctorsCache: Doctor[] = [];
    private destroy$ = new Subject<void>();

    // ── Dialog / nav state ───────────────────────────────────────────────────
    editVisible = false;
    viewVisible = false;
    deleteConfirmVisible = false;
    editModel: Partial<Patient> | null = null;
    viewModel: Patient | null = null;
    deleteModel: Patient | null = null;
    currentNav: 'dashboard' | 'queue' | 'manage-doctors' = 'queue';
    sidebarOpen = false;

    constructor(
        private messageService: MessageService,
        private route: ActivatedRoute,
        private router: Router,
        private confirmationService: ConfirmationService,
        private queueService: QueueService,
        private doctorService: DoctorService,
        private receptionService: ReceptionService,
        private authService: AuthService,
        private notificationService: NotificationService,
        private elRef: ElementRef
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

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── Close panel when clicking outside ────────────────────────────────────
    @HostListener('document:click', ['$event'])
    onDocumentClick(event: MouseEvent) {
        if (!this.filterPanelOpen) return;
        const panel = this.elRef.nativeElement.querySelector('.filter-panel-wrapper');
        if (panel && !panel.contains(event.target as Node)) {
            this.filterPanelOpen = false;
        }
    }

    toggleFilterPanel(event: MouseEvent) {
        event.stopPropagation();
        this.filterPanelOpen = !this.filterPanelOpen;
    }

    clearAllFilters() {
        this.selectedStatus = null;
        this.paymentFilter = null;
        this.selectedDoctorId = null;
        this.selectedDepartment = null;
        this.sortField = 'token';
        this.sortDir = 'asc';
        this.filter();
    }

    applyAndClose() {
        this.filterPanelOpen = false;
        this.filter();
    }

    setSortField(field: SortField) {
        if (this.sortField === field) {
            this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortField = field;
            this.sortDir = 'asc';
        }
        this.filter();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
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

    private parseAge(raw: any): number {
        if (raw === null || raw === undefined || raw === '') return 0;
        let str = raw.toString().trim();
        str = str.replace(/^(age|patient|p|age-|patient_)?[-_]*/i, '');
        const cleaned = str.replace(/[^0-9]/g, '');
        const parsed = parseInt(cleaned, 10);
        return isNaN(parsed) || parsed < 0 ? 0 : Math.min(parsed, 150);
    }

    private mapStatus(raw: string): 'pending' | 'completed' | 'skipped' {
        const s = (raw || '').toLowerCase();
        if (s === 'done' || s === 'completed') return 'completed';
        if (s === 'skipped') return 'skipped';
        return 'pending';
    }

    // ── Queue loading ─────────────────────────────────────────────────────────
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

    // ── Core filter + sort ────────────────────────────────────────────────────
    filter() {
        // 1. Split skipped vs non-skipped
        let skipped = this.tokens.filter(t => t.status === 'skipped');
        let nonSkipped = this.tokens.filter(t => t.status !== 'skipped');

        // 2. If user explicitly filtered to "skipped" only
        if (this.selectedStatus === 'skipped') {
            skipped = this.applyCommonFilters(skipped);
            this.filteredTokens = this.applySort(this.applySearch(skipped));
            return;
        }

        // 3. Apply status filter to non-skipped
        if (this.selectedStatus) {
            nonSkipped = nonSkipped.filter(t => t.status === this.selectedStatus);
        }

        // 4. Common filters (payment, doctor, department) to both groups
        skipped = this.applyCommonFilters(skipped);
        nonSkipped = this.applyCommonFilters(nonSkipped);

        // 5. Search
        if (this.searchText.trim()) {
            const q = this.searchText.toLowerCase();
            skipped = skipped.filter(t =>
                t.name.toLowerCase().includes(q) || t.token.toLowerCase().includes(q));
            nonSkipped = nonSkipped.filter(t =>
                t.name.toLowerCase().includes(q) || t.token.toLowerCase().includes(q));
        }

        // 6. Sort each group, skipped always on top
        const sortedSkipped = this.applySort(skipped);
        const sortedNonSkipped = this.applySort(nonSkipped);
        this.filteredTokens = [...sortedSkipped, ...sortedNonSkipped];
    }

    private applyCommonFilters(list: Patient[]): Patient[] {
        if (this.paymentFilter) {
            list = list.filter(t => (t.paymentStatus || 'unpaid') === this.paymentFilter);
        }
        if (this.selectedDoctorId) {
            list = list.filter(t => t.doctorId === this.selectedDoctorId);
        }
        if (this.selectedDepartment) {
            list = list.filter(t => (t.department || '') === this.selectedDepartment);
        }
        return list;
    }

    private applySearch(list: Patient[]): Patient[] {
        if (!this.searchText.trim()) return list;
        const q = this.searchText.toLowerCase();
        return list.filter(t =>
            t.name.toLowerCase().includes(q) || t.token.toLowerCase().includes(q));
    }

    private applySort(list: Patient[]): Patient[] {
        return [...list].sort((a, b) => {
            let valA = '';
            let valB = '';
            switch (this.sortField) {
                case 'token':
                    // Numeric sort on token number portion
                    const numA = parseInt((a.token || '').replace(/\D/g, ''), 10) || 0;
                    const numB = parseInt((b.token || '').replace(/\D/g, ''), 10) || 0;
                    return this.sortDir === 'asc' ? numA - numB : numB - numA;
                case 'name': valA = a.name || ''; valB = b.name || ''; break;
                case 'status': valA = a.status || ''; valB = b.status || ''; break;
                case 'payment': valA = a.paymentStatus || ''; valB = b.paymentStatus || ''; break;
                case 'department': valA = a.department || ''; valB = b.department || ''; break;
                case 'doctor': valA = a.doctorName || ''; valB = b.doctorName || ''; break;
            }
            const cmp = valA.localeCompare(valB);
            return this.sortDir === 'asc' ? cmp : -cmp;
        });
    }

    onSearchChange(text: string) { this.searchText = text; this.filter(); }
    onFilterChange() { this.filter(); }
    save() { this.messageService.add({ severity: 'success', summary: 'Saved', detail: 'Queue saved (in-memory)' }); }

    // ── Row actions ───────────────────────────────────────────────────────────
    view(row: Patient) { this.viewModel = row; this.viewVisible = true; }

    edit(row: Patient) {
        this.editModel = { ...row, age: this.parseAge(row.age) };
        this.editVisible = true;
    }

    onAgeChange(value: any): void {
        if (this.editModel) this.editModel.age = this.parseAge(value);
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
        if (mapped.phone) updated.patient_phone = mapped.phone;

        this.receptionService.updateToken(mapped.id, updated)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: () => {
                    this.tokens[idx] = { ...this.tokens[idx], ...(this.editModel as Patient), age: safeAge };
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
        if (tokenIndex > -1) this.filteredTokens.splice(tokenIndex, 1);

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
                        this.messageService.add({
                            severity: 'error', summary: 'Backend Error',
                            detail: `Failed to update token status. Status still: ${updatedStatus}. Contact admin.`, life: 5000
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

    // ── Nav & misc ────────────────────────────────────────────────────────────
    navigateTo(page: 'dashboard' | 'queue' | 'manage-doctors') {
        this.currentNav = page;
        this.sidebarOpen = false;
        if (page === 'dashboard') this.router.navigate(['../dashboard'], { relativeTo: this.route });
        else if (page === 'queue') this.router.navigate(['../queue'], { relativeTo: this.route });
        else if (page === 'manage-doctors') this.router.navigate(['../manage-doctors'], { relativeTo: this.route });
    }

    toggleSidebar(): void { this.sidebarOpen = !this.sidebarOpen; }

    private drawRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    downloadSlip(row: Patient): void {
        this.messageService.add({ severity: 'info', summary: 'Downloading', detail: 'Generating slip...', life: 2000 });

        setTimeout(() => {
            const W = 600, H = 1020;
            const canvas = document.createElement('canvas');
            canvas.width = W;
            canvas.height = H;
            const ctx = canvas.getContext('2d')!;

            const drawSlip = (logoImg: HTMLImageElement | null) => {
                // ── Background ──────────────────────────────────────────────────────────
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, W, H);

                // ── Outer border ────────────────────────────────────────────────────────
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 2;
                ctx.strokeRect(18, 18, W - 36, H - 36);

                let y = 40;

                // ── Logo ────────────────────────────────────────────────────────────────
                if (logoImg) {
                    ctx.drawImage(logoImg, W / 2 - 36, y, 72, 72);
                    y += 80;
                } else {
                    y += 12;
                }

                // ── Hospital name ────────────────────────────────────────────────────────
                ctx.fillStyle = '#000000';
                ctx.font = 'bold 17px Arial';
                ctx.textAlign = 'center';
                ctx.fillText('Rufayda Health Complex', W / 2, y);
                y += 18;

                ctx.font = '11px Arial';
                ctx.fillStyle = '#444444';
                ctx.fillText('Soan Gardens, Islamabad  |  +92 335 2015268', W / 2, y);
                y += 28;

                // ── Divider ──────────────────────────────────────────────────────────────
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(W - 36, y); ctx.stroke();
                y += 18;

                // ── "TOKEN SLIP" heading ─────────────────────────────────────────────────
                ctx.font = 'bold 11px Arial';
                ctx.fillStyle = '#000000';
                ctx.textAlign = 'center';
                ctx.fillText('TOKEN SLIP', W / 2, y);
                y += 28;

                // ── Large token number (same as patient ticket) ──────────────────────────
                ctx.font = 'bold 72px Arial';
                ctx.fillStyle = '#000000';
                ctx.textAlign = 'center';
                ctx.fillText(row.token || '-', W / 2, y + 60);
                y += 80;

                // ── Status pill ──────────────────────────────────────────────────────────
                const status = (row.status || 'pending').toUpperCase();
                const pillW = 120, pillH = 26, pillX = W / 2 - 60;
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 1.5;
                this.drawRoundRect(ctx, pillX, y, pillW, pillH, 4);
                ctx.stroke();
                ctx.font = 'bold 10px Arial';
                ctx.fillStyle = '#000000';
                ctx.textAlign = 'center';
                ctx.fillText(status, W / 2, y + 17);
                y += 44;

                // ── Light divider ─────────────────────────────────────────────────────────
                ctx.strokeStyle = '#cccccc';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(W - 36, y); ctx.stroke();
                y += 20;

                // ── Helpers ──────────────────────────────────────────────────────────────
                const ROW_H = 26;

                const drawRow = (label: string, value: string, rowY: number, shaded: boolean) => {
                    if (shaded) {
                        ctx.fillStyle = '#f5f5f5';
                        ctx.fillRect(36, rowY - 14, W - 72, 24);
                    }
                    ctx.font = '11px Arial';
                    ctx.fillStyle = '#555555';
                    ctx.textAlign = 'left';
                    ctx.fillText(label, 48, rowY + 4);
                    ctx.font = 'bold 11px Arial';
                    ctx.fillStyle = '#000000';
                    ctx.textAlign = 'right';
                    ctx.fillText(value, W - 48, rowY + 4);
                };

                const drawSection = (text: string, headerY: number) => {
                    ctx.font = 'bold 10px Arial';
                    ctx.fillStyle = '#000000';
                    ctx.textAlign = 'left';
                    ctx.fillText(text.toUpperCase(), 48, headerY);
                    ctx.strokeStyle = '#000000';
                    ctx.lineWidth = 0.5;
                    ctx.beginPath(); ctx.moveTo(36, headerY + 6); ctx.lineTo(W - 36, headerY + 6); ctx.stroke();
                };

                // ── Appointment Info ──────────────────────────────────────────────────────
                drawSection('Appointment Info', y); y += 18;
                drawRow('Hospital', 'Rufayda Health Complex', y, false); y += ROW_H;
                drawRow('Department', row.department || '-', y, true); y += ROW_H;
                drawRow('Doctor', row.doctorName || 'Any', y, false); y += ROW_H + 10;

                // ── Patient Details ───────────────────────────────────────────────────────
                drawSection('Patient Details', y); y += 18;
                drawRow('Name', row.name || '-', y, false); y += ROW_H;
                drawRow('MRN', row.mrn || '-', y, true); y += ROW_H;
                drawRow('Phone', row.phone || '-', y, false); y += ROW_H;
                drawRow('Age', (row.age ?? '-') + ' years', y, true); y += ROW_H;
                drawRow('Gender', row.gender || '-', y, false); y += ROW_H + 10;

                // ── Reason for Visit ──────────────────────────────────────────────────────
                if (row.reason) {
                    drawSection('Reason for Visit', y); y += 18;
                    ctx.font = '10px Arial';
                    ctx.fillStyle = '#333333';
                    ctx.textAlign = 'left';
                    const words = row.reason.split(' ');
                    let line = '';
                    for (const word of words) {
                        const test = line ? line + ' ' + word : word;
                        if (ctx.measureText(test).width > W - 96 && line) {
                            ctx.fillText(line, 48, y); y += 16; line = word;
                        } else { line = test; }
                    }
                    if (line) { ctx.fillText(line, 48, y); y += 16; }
                    y += 10;
                }

                // ── Bottom divider & footer ───────────────────────────────────────────────
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(36, H - 56); ctx.lineTo(W - 36, H - 56); ctx.stroke();

                ctx.font = '10px Arial';
                ctx.fillStyle = '#777777';
                ctx.textAlign = 'center';
                ctx.fillText('Please keep this slip for your records.  For assistance, contact reception.', W / 2, H - 38);
                ctx.fillText('Rufayda Health Complex  -  Soan Gardens, Islamabad', W / 2, H - 22);

                // ── Export ───────────────────────────────────────────────────────────────
                canvas.toBlob((blob) => {
                    if (!blob) return;
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = `token-${row.token}.png`;
                    link.click();
                    URL.revokeObjectURL(url);
                    this.messageService.add({ severity: 'success', summary: 'Downloaded', detail: 'Slip saved.', life: 3000 });
                });
            };

            const img = new Image();
            img.onload = () => drawSlip(img);
            img.onerror = () => drawSlip(null);
            img.src = 'assets/rufaydaLogo.jpg';
        }, 500);
    }
    private getStatusColor(status: string): string {
        const statusColors: { [key: string]: string } = {
            'pending': '#f97316',
            'waiting': '#3b82f6',
            'called': '#8b5cf6',
            'completed': '#22c55e',
            'cancelled': '#ef4444',
            'skipped': '#ec4899'
        };
        return statusColors[status.toLowerCase()] || '#6b7280';
    }

    signOut() { this.router.navigate(['/']); }
}