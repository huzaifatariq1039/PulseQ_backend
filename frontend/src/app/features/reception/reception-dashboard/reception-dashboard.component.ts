import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { DropdownModule } from 'primeng/dropdown';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { InputTextModule } from 'primeng/inputtext';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { CheckboxModule } from 'primeng/checkbox';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { QueueService } from '../../../core/services/queue.service';
import { ConsultationService } from '../../../core/services/consultation.service';
import { Token } from '../../../shared/models/token.model';
import { ReceptionSidebarComponent } from '../shared/components/reception-sidebar/reception-sidebar.component';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Doctor } from '../../../shared/models/doctor.model';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { ReceptionService } from '../../../core/services/reception.service';
import { DoctorService } from '../../../core/services/doctor.service';
import { AuthService } from '../../../core/services/auth.service';

interface Patient {
  id?: string;
  token: string;
  name: string;
  age: number;
  gender: string;
  reason: string;
  status?: 'pending' | 'completed' | 'skipped' | 'inProgress';
  department?: string;
  phone?: string;
  paymentStatus?: 'paid' | 'unpaid';
  fee?: string;
  estimatedWait?: number | string;
}

@Component({
  selector: 'app-reception-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardModule,
    ButtonModule,
    DropdownModule,
    DialogModule,
    ToastModule,
    InputTextModule,
    InputTextareaModule,
    CheckboxModule,
    TooltipModule,
    ReceptionSidebarComponent
  ],
  providers: [MessageService],
  templateUrl: './reception-dashboard.component.html',
  styleUrls: ['./reception-dashboard.component.css']
})
export class ReceptionDashboardComponent implements OnInit, OnDestroy {

  doctorData: Doctor[] = [];
  selectedDoctorInfo: Doctor | null = null;
  departments: { label: string; value: string }[] = [];

  doctors: { label: string; value: string | null }[] = [
    { label: 'Choose a specific doctor...', value: null }
  ];

  genders = [
    { label: 'Male', value: 'Male' },
    { label: 'Female', value: 'Female' },
    { label: 'Other', value: 'Other' }
  ];

  selectedDepartment: string | null = null;

  current: Patient | null = null;
  upcoming: Patient[] = [];
  allUpcoming: Patient[] = [];
  allTokens: Patient[] = [];
  skippedTokens: Patient[] = [];

  waitingCount = 0;
  completedCount = 0;
  skippedCount = 0;
  avgWait = 0;

  showWalkIn = false;
  currentNav: 'dashboard' | 'queue' | 'manage-doctors' = 'dashboard';
  sidebarOpen = false;

  walkIn: any = {
    department: null,
    doctor: null,
    assignAnyDoctor: false,
    phone: '',
    name: '',
    age: null,
    gender: 'Male',
    reason: '',
    paymentStatus: 'unpaid',
    specialInstructions: ''
  };

  walkInTouched: { [key: string]: boolean } = {};

  private destroy$ = new Subject<void>();

  // localStorage key scoped per hospital so multiple hospitals don't bleed into each other
  private get skippedStorageKey(): string {
    return `skippedTokens_${this.getHospitalId()}`;
  }

  constructor(
    private router: Router,
    private messageService: MessageService,
    private queueService: QueueService,
    private consultationService: ConsultationService,
    private staffService: StaffPortalService,
    private receptionService: ReceptionService,
    private doctorService: DoctorService,
    private authService: AuthService
  ) { }

  ngOnInit() {
    // Restore skipped tokens from localStorage FIRST so the panel is visible immediately on refresh
    this.loadSkippedFromStorage();
    this.loadDepartments();
    this.loadDoctors();
    // Load queue first, then stats — ordering matters for skipped state
    this.loadQueueThenStats();
  }

  private getHospitalId(): string {
    const user: any = this.authService.getCurrentUser();
    return user?.hospitalId || user?.hospital_id || '';
  }

  // ── SKIPPED TOKEN PERSISTENCE (localStorage) ──
  // These three methods are the workaround for the backend not returning
  // SKIPPED tokens in the queue response. Once the backend is fixed,
  // syncSkippedFromAllTokens() will handle everything and these
  // localStorage methods become a safety net only.

  private saveSkippedToStorage(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(this.skippedStorageKey, JSON.stringify(this.skippedTokens));
      }
    } catch (e) { /* ignore */ }
  }

  private loadSkippedFromStorage(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const raw = window.localStorage.getItem(this.skippedStorageKey);
        if (raw) {
          this.skippedTokens = JSON.parse(raw);
          this.skippedCount = this.skippedTokens.length;
        }
      }
    } catch (e) { /* ignore */ }
  }

  private removeFromSkippedStorage(token: string): void {
    this.skippedTokens = this.skippedTokens.filter(t => t.token !== token);
    this.skippedCount = this.skippedTokens.length;
    this.saveSkippedToStorage();
  }

  // ── QUEUE LOADING ──

  /**
   * Loads queue first → then dashboard stats.
   * Chained so allTokens is ready before stats potentially overwrites allUpcoming.
   */
  loadQueueThenStats(): void {
    this.receptionService.getQueue(this.getHospitalId())
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          this.processQueueResponse(res);
          this.loadDashboardStats();
        },
        error: (err) => {
          console.error('Failed to load queue in dashboard', err);
          this.loadDashboardStats();
        }
      });
  }

  /**
   * Maps raw queue API response into allTokens, derives skipped/current/upcoming.
   *
   * BACKEND BUG NOTE:
   * The queue endpoint currently returns data:[] — it filters out SKIPPED tokens.
   * When this is empty, we fall back to localStorage skipped tokens so the panel
   * doesn't disappear on refresh. Once the backend fix is applied (see backend notes
   * below), backendSkipped.length will be > 0 and localStorage becomes just a cache.
   */
  private processQueueResponse(res: any): void {
    const rawTokens = res?.data || res?.queue || res || [];
    const tokensArray = Array.isArray(rawTokens) ? rawTokens : [];

    this.allTokens = tokensArray.map((t: any) => {
      const statusRaw = t.status || t.state || 'WAITING';
      let mappedStatus: 'pending' | 'completed' | 'skipped' | 'inProgress' = 'pending';
      if (statusRaw === 'IN_PROGRESS') mappedStatus = 'inProgress';
      else if (statusRaw === 'WAITING' || statusRaw === 'pending') mappedStatus = 'pending';
      else if (statusRaw === 'DONE' || statusRaw === 'completed') mappedStatus = 'completed';
      else if (statusRaw === 'SKIPPED' || statusRaw === 'skipped') mappedStatus = 'skipped';

      return {
        token: t.token_number || t.tokenNumber || t.token || 'T-00',
        name: t.patient_name || t.patientName || t.patientId || 'Unknown',
        age: t.patient_age || t.patientAge || 0,
        gender: t.patient_gender || t.patientGender || 'Unknown',
        reason: t.reason_for_visit || t.reasonForVisit || t.reason || '',
        status: mappedStatus,
        department: t.department || 'General Medicine',
        phone: t.patient_phone || t.patientPhone || t.phone || '',
        paymentStatus: t.payment_status || t.paymentStatus || 'unpaid',
        mrn: t.mrn || t.patient_id || '-',
        id: t.token_id || t.id || t.tokenId || ''
      } as any;
    });

    const backendSkipped = this.allTokens.filter(t => t.status === 'skipped');

    if (backendSkipped.length > 0) {
      // Backend is correctly returning skipped tokens — use as source of truth
      this.skippedTokens = backendSkipped;
      this.skippedCount = this.skippedTokens.length;
      this.saveSkippedToStorage();
    } else {
      // Backend not returning skipped tokens (current bug) — keep localStorage version
      // loadSkippedFromStorage() already ran in ngOnInit so skippedTokens is intact
    }

    this.completedCount = this.allTokens.filter(t => t.status === 'completed').length;

    const inProgress = this.allTokens.find(x => x.status === 'inProgress');
    if (inProgress) {
      this.current = inProgress;
    } else {
      const waitingTokens = this.allTokens.filter(x => x.status === 'pending');
      this.current = waitingTokens.length ? waitingTokens[0] : null;
    }

    this.allUpcoming = this.allTokens.filter(
      t => t.status === 'pending' && t.token !== this.current?.token
    );
    this.filterByDepartment();
  }

  /** Public alias for manual refresh (walk-in, re-add, etc.) */
  loadQueue(): void {
    this.loadQueueThenStats();
  }

  loadDepartments(): void {
    const hid = this.getHospitalId();
    this.doctorService.listDepartments(hid).pipe(takeUntil(this.destroy$)).subscribe({
      next: (res: any) => {
        const depts = res?.departments || res?.data || (Array.isArray(res) ? res : []);
        if (Array.isArray(depts) && depts.length > 0) {
          this.departments = depts.map((d: any) => {
            const name = typeof d === 'string' ? d : (d.name || d.label || d.department || '');
            return { label: name, value: name };
          });
        }
      },
      error: (err) => console.error('Failed to load departments from API', err)
    });
  }

  loadDashboardStats(): void {
    const hid = this.getHospitalId();
    this.staffService.getReceptionistDashboard(hid).pipe(takeUntil(this.destroy$)).subscribe({
      next: (res: any) => {
        const data = res?.data || res || {};

        if (data.now_serving) {
          const nowServing = data.now_serving;
          this.current = {
            token: nowServing.token_number || nowServing.tokenNumber || 'T-00',
            name: nowServing.patient_name || nowServing.patientName || 'Unknown',
            age: this.parseAge(nowServing.patient_age) || 0,
            gender: nowServing.patient_gender || nowServing.patientGender || 'Unknown',
            reason: nowServing.reason || nowServing.reason_for_visit || 'General Medicine',
            department: nowServing.department || 'General Medicine',
            phone: nowServing.patient_phone || '',
            status: 'inProgress',
            id: nowServing.token_id || nowServing.id || ''
          };
        }

        if (data.cards) {
          this.waitingCount = data.cards.waiting || 0;
          this.completedCount = data.cards.completed || 0;
          this.avgWait = data.cards.avg_wait_minutes || 0;
          // Prefer local skipped list (has actual objects); fall back to API count
          this.skippedCount = this.skippedTokens.length > 0
            ? this.skippedTokens.length
            : (data.cards.skipped || 0);
        } else if (data.stats) {
          if (data.stats.waiting !== undefined) this.waitingCount = data.stats.waiting;
          if (data.stats.completed !== undefined) this.completedCount = data.stats.completed;
          this.avgWait = data.stats.avg_wait_time;
          this.skippedCount = this.skippedTokens.length > 0
            ? this.skippedTokens.length
            : (data.stats.skipped || 0);
        }

        // Use active_doctors from dashboard if doctorData not yet loaded
        if (data.active_doctors && Array.isArray(data.active_doctors) && this.doctorData.length === 0) {
          this.doctorData = data.active_doctors.map((d: any) => ({
            id: d.doctor_id,
            name: d.doctor_name,
            specialization: d.department,
            qualifications: '',
            timings: '',
            available: d.status === 'available',
            onLeave: d.status === 'on_leave',
            fee: '',
            department: d.department
          }));
        }

        if (data.upcoming_queue && Array.isArray(data.upcoming_queue)) {
          this.allUpcoming = data.upcoming_queue.map((t: any) => ({
            token: t.token_number || t.tokenNumber || t.token || 'T-00',
            name: t.patient_name || t.patientName || t.name || 'Unknown',
            age: this.parseAge(t.patient_age) || 0,
            gender: t.patient_gender || t.patientGender || t.gender || 'Unknown',
            reason: t.reason || t.reason_for_visit || t.reasonForVisit || '',
            department: t.department || 'General Medicine',
            phone: t.phone || t.patient_phone || '',
            status: t.status || 'pending',
            estimatedWait: t.waiting_time_minutes || t.estimated_wait_time || t.estimated_wait || t.wait_time || 15,
            mrn: t.mrn || t.patient_id || '-',
            id: t.token_id || t.id || ''
          }));

          // Do NOT call syncSkippedFromAllTokens() here — allTokens is empty (backend bug)
          // skippedTokens is already correctly populated from localStorage
          this.filterByDepartment();
        }
      },
      error: (err) => console.warn('Failed to load dashboard stats from API', err)
    });
  }

  private parseAge(ageStr: any): number {
    if (!ageStr) return 0;
    if (typeof ageStr === 'number') return ageStr;
    const match = String(ageStr).match(/\d+/);
    return match ? parseInt(match[0], 10) : 0;
  }

  loadDoctors(): void {
    this.doctorService.manageDoctors().pipe(takeUntil(this.destroy$)).subscribe({
      next: (res: any) => {
        const docs = res?.data || res?.doctors || res || [];
        this.doctorData = Array.isArray(docs) ? docs.map((d: any) => ({
          id: d.id || d.doctor_id,
          name: d.name,
          specialization: d.department,
          qualifications: d.qualifications || '',
          timings: `${this.convertTo12Hour(d.start_time)} - ${this.convertTo12Hour(d.end_time)}`,
          available: d.status === 'available',
          onLeave: d.status === 'on_leave',
          fee: `Rs. ${d.consultation_fee || 0}`,
          department: d.department
        })) : [];
        this.updateDoctorsDropdown();
      },
      error: (err) => console.error('Failed to load doctors in dashboard', err)
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── HELPERS ──

  convertTo12Hour(time24: string): string {
    if (!time24) return '9:00 AM';
    const [hours, minutes] = time24.split(':');
    const hour = parseInt(hours, 10);
    const min = minutes || '00';
    const period = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 === 0 ? 12 : hour % 12;
    return `${hour12}:${min} ${period}`;
  }

  onDepartmentChangeWalkIn(): void {
    this.walkIn.doctor = null;
    this.walkIn.assignAnyDoctor = false;
    this.selectedDoctorInfo = null;
    this.updateDoctorsDropdown();
    const dept = this.walkIn.department;
    const availableDoctorsForDept = this.doctorData.filter(d => !dept || d.department === dept);
    if (availableDoctorsForDept.length === 0) {
      this.messageService.add({
        severity: 'warn', summary: 'No Doctors Available',
        detail: `No doctors available for ${dept} department`, life: 3000
      });
    }
  }

  updateDoctorsDropdown(): void {
    const dept = this.walkIn.department;
    this.doctors = [
      { label: 'Choose a specific doctor...', value: null },
      ...this.doctorData
        .filter(d => !dept || d.department === dept)
        .map(d => ({ label: d.name, value: d.id as string }))
    ];
  }

  onDoctorChange(doctorId: string | null): void {
    this.selectedDoctorInfo = doctorId
      ? (this.doctorData.find(d => d.id === doctorId) || null)
      : null;
  }

  onAssignAnyDoctorChange(checked: boolean): void {
    if (checked) {
      const dept = this.walkIn.department;
      const available = this.doctorData.filter(d => d.available && (!dept || d.department === dept));
      if (available.length > 0) {
        const random = available[Math.floor(Math.random() * available.length)];
        this.walkIn.doctor = random.id;
        this.selectedDoctorInfo = random;
      } else {
        this.messageService.add({
          severity: 'warn', summary: 'No Available Doctors',
          detail: 'No available doctors found for the selected department.', life: 3000
        });
        this.walkIn.assignAnyDoctor = false;
      }
    } else {
      this.walkIn.doctor = null;
      this.selectedDoctorInfo = null;
    }
  }

  onDepartmentChange(): void { this.filterByDepartment(); }

  filterByDepartment(): void {
    this.upcoming = this.allUpcoming.filter(patient => {
      const dept = (patient.department as string) ?? 'General Medicine';
      return !this.selectedDepartment || dept === this.selectedDepartment;
    });
    this.waitingCount = this.upcoming.length;
  }

  private refreshUpcomingList(): void {
    this.allUpcoming = this.allTokens.filter(
      t => t.status === 'pending' && t.token !== this.current?.token
    );
    this.filterByDepartment();
  }

  /**
   * Re-derives skipped from allTokens and persists.
   * Only reliable when allTokens is populated (i.e. after backend fix).
   * For the current backend bug, use saveSkippedToStorage() directly.
   */
  private syncSkippedFromAllTokens(): void {
    this.skippedTokens = this.allTokens.filter(t => t.status === 'skipped');
    this.skippedCount = this.skippedTokens.length;
    this.saveSkippedToStorage();
  }

  saveQueue(): void {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem('receptionQueue', JSON.stringify({
          current: this.current, allTokens: this.allTokens
        }));
      }
    } catch (e) { /* ignore */ }
  }

  completeCurrent(): void {
    if (!this.current) return;
    const arr = this.queueService.getQueueSnapshot();
    const found = arr.find(x => x.tokenNumber === this.current!.token);
    if (found) {
      this.queueService.updateTokenStatus(found.id, 'DONE');
      this.messageService.add({
        severity: 'success', summary: 'Completed', detail: this.current!.token, life: 2000
      });
      const tokenInAll = this.allTokens.find(t => t.token === this.current!.token);
      if (tokenInAll) tokenInAll.status = 'completed';
      this.completedCount = this.allTokens.filter(t => t.status === 'completed').length;
      const nextWaiting = this.allTokens.find(t => t.status === 'pending');
      this.current = nextWaiting || null;
      this.refreshUpcomingList();
      this.syncSkippedFromAllTokens();
    }
  }

  skipCurrent(): void {
    if (!this.current) return;

    const tokenId = (this.current as any).id || (this.current as any).tokenId;
    if (!tokenId) {
      this.messageService.add({
        severity: 'error', summary: 'Error',
        detail: 'Token ID not found, cannot skip.', life: 3000
      });
      return;
    }

    // Snapshot current patient before it gets cleared
    const skippedPatient: Patient = { ...this.current, status: 'skipped' };

    this.receptionService.skipToken(tokenId).subscribe({
      next: () => {
        const tokenInAll = this.allTokens.find(t => t.token === skippedPatient.token);
        if (tokenInAll) {
          // allTokens has this token — update and sync
          tokenInAll.status = 'skipped';
          this.syncSkippedFromAllTokens();
        } else {
          // allTokens is empty (backend bug) — manually push to skipped and persist
          const alreadyExists = this.skippedTokens.find(t => t.token === skippedPatient.token);
          if (!alreadyExists) {
            this.skippedTokens = [...this.skippedTokens, skippedPatient];
            this.skippedCount = this.skippedTokens.length;
            this.saveSkippedToStorage();
          }
        }

        this.messageService.add({
          severity: 'warn', summary: 'Skipped',
          detail: `${skippedPatient.token} moved to skipped`, life: 2500
        });

        const nextWaiting = this.allTokens.find(t => t.status === 'pending');
        this.current = nextWaiting || null;
        this.refreshUpcomingList();
      },
      error: (err) => {
        console.error('Failed to skip token', err);
        this.messageService.add({
          severity: 'error', summary: 'Error',
          detail: err?.error?.message || 'Failed to skip token', life: 3000
        });
      }
    });
  }

  reAddToQueue(patient: Patient): void {
    if (!patient.id) {
      this.messageService.add({
        severity: 'error', summary: 'Error', detail: 'Patient ID not found', life: 3000
      });
      return;
    }
    this.receptionService.reAddToken(patient.id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response: any) => {
          const updatedStatus = response?.data?.status;
          if (updatedStatus && updatedStatus.toLowerCase() !== 'skipped') {
            this.messageService.add({
              severity: 'success', summary: 'Re-added to Queue',
              detail: `${patient.token} — ${patient.name}`, life: 3000
            });

            const tokenInAll = this.allTokens.find(t => t.token === patient.token);
            if (tokenInAll) {
              tokenInAll.status = 'pending';
              this.syncSkippedFromAllTokens();
            } else {
              // allTokens empty (backend bug) — remove directly from storage
              this.removeFromSkippedStorage(patient.token);
            }

            this.refreshUpcomingList();
          } else {
            console.error('Backend bug: token status not updated. Response:', response?.data);
            this.messageService.add({
              severity: 'error', summary: 'Backend Error',
              detail: `Backend failed to update token status. Still: ${updatedStatus}. Contact admin.`,
              life: 5000
            });
          }
          setTimeout(() => this.loadQueueThenStats(), 500);
        },
        error: (err) => {
          console.error('Failed to re-add token:', err);
          this.messageService.add({
            severity: 'error', summary: 'Error',
            detail: 'Failed to re-add patient to queue', life: 3000
          });
        }
      });
  }

  addWalkIn(): void {
    if (!this.isNameValid(this.walkIn.name)) {
      this.messageService.add({
        severity: 'error', summary: 'Error',
        detail: this.hasNumbersInName(this.walkIn.name)
          ? 'Patient Name cannot contain numbers'
          : 'Patient Name is required and must contain only letters',
        life: 3000
      });
      return;
    }
    if (!this.isAgeValid(this.walkIn.age)) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Please enter a valid age (1-150)', life: 3000 });
      return;
    }
    if (!this.walkIn.gender) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Gender is required', life: 3000 });
      return;
    }
    if (!this.walkIn.department) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Department is required', life: 3000 });
      return;
    }
    if (!this.isPhoneValid(this.walkIn.phone)) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Phone must be numeric (exactly 11 digits)', life: 3000 });
      return;
    }
    if (!this.walkIn.reason || !this.walkIn.reason.trim()) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Reason for Visit is required', life: 3000 });
      return;
    }

    const patientId = `WALKIN-${Date.now()}`;
    let doctorName = 'Any';
    let doctorId = '';
    let fee = '-';

    if (this.walkIn.doctor) {
      const selectedDoc = this.doctorData.find(d => d.id === this.walkIn.doctor);
      doctorName = selectedDoc?.name || 'Any';
      doctorId = this.walkIn.doctor;
    }

    const extras = {
      patientName: this.walkIn.name,
      patientPhone: this.walkIn.phone,
      patientAge: this.walkIn.age,
      patientGender: this.walkIn.gender,
      reasonForVisit: this.walkIn.reason,
      specialNotes: this.walkIn.specialInstructions,
      doctor: doctorName,
      paymentStatus: this.walkIn.paymentStatus
    };

    this.receptionService.createWalkInToken(
      this.getHospitalId(),
      doctorId || '',
      this.walkIn.name,
      this.walkIn.phone,
      this.walkIn.age ? this.walkIn.age.toString() : '',
      typeof this.walkIn.gender === 'object' && this.walkIn.gender !== null
        ? this.walkIn.gender.value
        : this.walkIn.gender,
      this.walkIn.reason
    ).subscribe({
      next: (res: any) => {
        const tokenNumber = res.data?.token_number || res.token?.token_number || 'Token';
        this.messageService.add({
          severity: 'success', summary: 'Token Generated',
          detail: `${tokenNumber} - ${this.walkIn.name}`, life: 3000
        });
        this.downloadSlip({
          token: tokenNumber,
          name: this.walkIn.name,
          phone: this.walkIn.phone,
          age: this.walkIn.age,
          gender: this.walkIn.gender,
          reason: this.walkIn.reason || '',
          department: this.walkIn.department || 'General Medicine',
          doctorName: doctorName,
          mrn: res.data?.mrn || res.data?.patient_id || '-',
          paymentStatus: this.walkIn.paymentStatus,
          status: 'pending',
          fee: res.data?.total_fee
            ? `Rs. ${res.data.total_fee}`
            : (res.data?.fee ? `Rs. ${res.data.fee}` : fee)
        } as Patient);
        this.resetWalkInForm();
        this.loadQueueThenStats();
      },
      error: (err) => {
        console.error('Failed to create walkin token API', err);
        const backendError = err.error?.message || 'Unknown API Error';
        this.messageService.add({
          severity: 'error', summary: 'Backend Rejected Payload',
          detail: backendError, life: 15000
        });
        const created = this.queueService.addTokenFor(
          patientId, doctorId,
          this.walkIn.department || 'General Medicine',
          extras as any
        );
        this.messageService.add({
          severity: 'success', summary: 'Token Generated (Offline)',
          detail: `${created.tokenNumber} - ${this.walkIn.name}`, life: 3000
        });
        this.downloadSlip({
          token: created.tokenNumber,
          name: this.walkIn.name,
          phone: this.walkIn.phone,
          age: this.walkIn.age,
          gender: this.walkIn.gender,
          reason: this.walkIn.reason || '',
          department: this.walkIn.department || 'General Medicine',
          doctorName: doctorName,
          mrn: '-',
          paymentStatus: this.walkIn.paymentStatus,
          status: 'pending',
          fee: fee
        } as Patient);
        this.resetWalkInForm();
        this.loadQueueThenStats();
      }
    });
  }

  resetWalkInForm(): void {
    this.walkIn = {
      department: null, doctor: null, assignAnyDoctor: false,
      phone: '', name: '', age: null, gender: 'Male',
      reason: '', paymentStatus: 'unpaid', specialInstructions: ''
    };
    this.selectedDoctorInfo = null;
    this.doctors = [{ label: 'Choose a specific doctor...', value: null }];
    this.walkInTouched = {};
    this.showWalkIn = false;
    this.filterByDepartment();
    this.saveQueue();
  }

  isNameValid(name: string): boolean {
    if (!name) return false;
    const trimmed = name.trim();
    return !!trimmed && /^[a-zA-Z\s]+$/.test(trimmed);
  }

  hasNumbersInName(name: string): boolean {
    return !!name && /[0-9]/.test(name);
  }

  isPhoneValid(phone: string): boolean {
    if (!phone) return false;
    const clean = phone.trim();
    return /^[0-9]+$/.test(clean) && clean.length === 11;
  }

  isAgeValid(age: any): boolean {
    if (!age && age !== 0) return false;
    const n = Number(age);
    return !isNaN(n) && Number.isInteger(n) && n > 0 && n <= 150;
  }

  navigateTo(page: 'dashboard' | 'queue' | 'manage-doctors'): void {
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
      canvas.width = 500;
      canvas.height = 600;
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
        ctx.fillText(`Doctor: ${(row as any).doctorName || 'Any'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Name: ${row.name || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Phone: ${row.phone || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`MRN: ${(row as any).mrn || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Age: ${row.age || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Gender: ${row.gender || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Payment: ${(row.paymentStatus || 'unpaid').toUpperCase()}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Fee: ${row.fee || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Status: ${(row.status || 'pending').toUpperCase()}`, canvas.width / 2, yPos);
      }
      canvas.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `ticket-${row.token}.png`;
          link.click();
          URL.revokeObjectURL(url);
          this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Slip downloaded successfully', life: 3000 });
        }
      });
    }, 1500);
  }

  signOut(): void { this.router.navigate(['/']); }
}