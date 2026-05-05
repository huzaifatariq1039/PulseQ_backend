import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { BadgeModule } from 'primeng/badge';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ConsultationService } from '../../../core/services/consultation.service';
import { QueueService } from '../../../core/services/queue.service';
import { Subscription, interval } from 'rxjs';
import { DoctorSidebarComponent } from '../shared/components/doctor-sidebar/doctor-sidebar.component';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AuthService } from '../../../core/services/auth.service';
import { NotificationService } from '../../../core/services/notification.service';
import { DoctorService } from '../../../core/services';

interface Patient {
  name: string;
  age: number;
  gender: string;
  reason: string;
  phone: string;
  token: string;
  patientId?: string;
  tokenId?: string;
  mrn?: string;
}

interface UpcomingPatient {
  token: string;
  name: string;
  age: number;
  reason: string;
  waitTime: string;
  patientId?: string;
  tokenId?: string;
  mrn?: string;
  gender?: string;
  phone?: string;
}

@Component({
  selector: 'app-doctor-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    FormsModule,
    ButtonModule,
    CardModule,
    InputTextareaModule,
    BadgeModule,
    ToastModule,
    DoctorSidebarComponent
  ],
  providers: [MessageService],
  templateUrl: './doctor-dashboard.component.html',
  styleUrl: './doctor-dashboard.component.css'
})
export class DoctorDashboardComponent implements OnInit, OnDestroy {

  doctorName = '';
  doctorId = '';
  specialty = '';
  qualifications = '';
  waitingPatients = 0;
  patientsServed = 0;
  rating = 0;
  reviewCount = 0;
  sidebarOpen = false;

  currentPatient: Patient | null = null;

  consultationNotes = '';
  consultationStartTime: Date | null = null;
  isConsultationActive = false;

  upcomingPatients: UpcomingPatient[] = [];
  skippedPatients: UpcomingPatient[] = [];

  private sub: Subscription | null = null;

  constructor(
    private router: Router,
    private messageService: MessageService,
    private consultationService: ConsultationService,
    private queueService: QueueService,
    private staffService: StaffPortalService,
    private authService: AuthService,
    private doctorService: DoctorService,
    private notificationService: NotificationService
  ) { }

  // =========================
  // START CONSULTATION
  // =========================
  startConsultation(): void {
    if (!this.currentPatient) return;

    const tokenId = this.currentPatient.tokenId;

    if (!tokenId) {
      console.error('Missing tokenId', this.currentPatient);
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Token ID is missing for this patient'
      });
      return;
    }

    if (!this.doctorId) {
      console.error('Missing doctorId');
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Doctor ID is missing. Please refresh the page.'
      });
      return;
    }

    const payload = { token_id: tokenId, doctor_id: this.doctorId };
    console.log('START consultation payload:', payload);

    this.consultationService.startConsultationApi(payload).subscribe({
      next: (res: any) => {
        console.log('Start consultation response:', res);
        this.consultationStartTime = new Date();
        this.isConsultationActive = true;

        // ✅ Remove current patient from upcoming queue immediately on start
        if (this.currentPatient?.tokenId) {
          this.upcomingPatients = this.upcomingPatients.filter(
            p => p.tokenId !== this.currentPatient!.tokenId &&
              p.token !== this.currentPatient!.token
          );
          console.log('[START] Removed serving patient from upcoming queue:', this.currentPatient.tokenId);
        }

        this.messageService.add({
          severity: 'info',
          summary: 'Consultation Started',
          detail: `With ${this.currentPatient?.name}`
        });
      },
      error: (err) => {
        console.error('Start consultation error', err);
        this.messageService.add({
          severity: 'error',
          summary: 'Failed to Start',
          detail: err?.error?.message || 'Could not start consultation. Please try again.'
        });
      }
    });
  }

  // =========================
  // FINISH CONSULTATION
  // =========================
  finishConsultation(): void {
    if (!this.currentPatient || !this.consultationStartTime) return;

    const tokenId = this.currentPatient.tokenId;

    if (!tokenId) {
      console.error('Missing tokenId', this.currentPatient);
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Token ID is missing for this patient'
      });
      return;
    }

    if (!this.doctorId) {
      console.error('Missing doctorId');
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Doctor ID is missing. Please refresh the page.'
      });
      return;
    }

    const payload = {
      token_id: tokenId,
      doctor_id: this.doctorId,
      consultation_notes: this.consultationNotes
    };

    console.log('END consultation payload:', payload);

    this.consultationService.endConsultationApi(payload).subscribe({
      next: (res: any) => {
        console.log('End consultation response:', res);
        this.messageService.add({
          severity: 'success',
          summary: 'Completed',
          detail: 'Consultation finished successfully'
        });

        this.patientsServed++;
        this.resetConsultation();
        this.fetchDashboard();
      },
      error: (err) => {
        console.error('End consultation error', err);
        this.messageService.add({
          severity: 'error',
          summary: 'Failed to Finish',
          detail: err?.error?.message || 'Could not finish consultation. Please try again.'
        });
      }
    });
  }

  // =========================
  // SKIP PATIENT
  // =========================
  skipPatient(): void {
    if (!this.currentPatient?.tokenId) return;

    const tokenId = this.currentPatient.tokenId;
    console.log('SKIP token_id:', tokenId);

    this.queueService.skipPatient(tokenId).subscribe({
      next: (res: any) => {
        console.log('Skip patient response:', res);
        this.messageService.add({
          severity: 'info',
          summary: 'Patient Skipped',
          detail: `${this.currentPatient?.name} has been moved to skipped queue`
        });
        // Send notification to patient about token being skipped
        if (this.currentPatient?.token) {
          this.notificationService.sendTokenSkipped(this.currentPatient.token, 'the doctor');
        }
        this.resetConsultation();
        this.fetchDashboard();
      },
      error: (err) => {
        console.error('Skip patient error', err);
        this.messageService.add({
          severity: 'error',
          summary: 'Skip Failed',
          detail: err?.error?.message || 'Could not skip patient. Please try again.'
        });
      }
    });
  }

  // =========================
  // RE-ADD FROM SKIPPED
  // =========================
  reAddFromSkipped(patient: UpcomingPatient): void {
    if (!patient.tokenId) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Patient token ID not found'
      });
      return;
    }

    console.log('RE-ADD token_id:', patient.tokenId);

    this.queueService.reAddToQueue(patient.tokenId).subscribe({
      next: (res: any) => {
        console.log('Re-add patient response:', res);
        this.messageService.add({
          severity: 'success',
          summary: 'Re-added',
          detail: `${patient.token} - ${patient.name} added back to queue`
        });
        this.fetchDashboard();
      },
      error: (err) => {
        console.error('Re-add patient error', err);
        this.messageService.add({
          severity: 'error',
          summary: 'Re-add Failed',
          detail: err?.error?.message || 'Could not re-add patient. Please try again.'
        });
      }
    });
  }

  // =========================
  // RESET
  // =========================
  private resetConsultation(): void {
    this.consultationNotes = '';
    this.consultationStartTime = null;
    this.isConsultationActive = false;
    this.currentPatient = null;
  }

  // =========================
  // INIT
  // =========================
  ngOnInit(): void {
    this.fetchDashboard();
    this.sub = interval(30000).subscribe(() => this.fetchDashboard());
  }

  // =========================
  // DASHBOARD
  // =========================
  fetchDashboard(): void {
    if (typeof window === 'undefined') return;

    // Fallback from auth (may be overridden by API response below)
    const currentUser = this.authService.getCurrentUser();
    if (currentUser) {
      this.doctorName = currentUser.name || '';
      this.doctorId = currentUser.id || '';
    }

    this.staffService.getDoctorDashboard(20, 20).subscribe({
      next: (res: any) => {
        if (!res.success) return;

        const d = res.data;

        // ✅ Use doctor ID from API response — this is the authoritative source
        if (d.doctor?.id) {
          this.doctorId = d.doctor.id;
          this.doctorName = d.doctor.name || this.doctorName;
          this.specialty = d.doctor.department || '';
        }

        console.log('Doctor ID from API:', this.doctorId);

        // ─── STEP 1: Build raw upcoming list ───────────────────────────────
        let rawUpcoming: UpcomingPatient[] = [];

        if (d.upcoming_patients && Array.isArray(d.upcoming_patients)) {
          rawUpcoming = d.upcoming_patients.map((t: any) => ({
            token: t.token_number || t.token || '',
            name: t.patient_name || 'Unknown',
            age: this.parseAge(t.patient_age) || 0,
            reason: t.reason_for_visit || t.reason || '',
            waitTime: (t.estimated_wait_time || t.waiting_time_minutes || 0) + 'm',
            patientId: t.patient_id || t.mrn || '',
            tokenId: t.token_id || t.id || '',
            mrn: t.mrn || '',
            gender: t.patient_gender || 'Unknown',
            phone: t.phone || ''
          }));
        }

        // ─── STEP 2: Resolve current patient ──────────────────────────────
        if (d.current_consultation) {
          // Backend says there IS an active consultation — use it authoritatively
          const t = d.current_consultation;
          this.currentPatient = {
            name: t.patient_name || 'Unknown',
            age: this.parseAge(t.patient_age) || 0,
            gender: t.patient_gender || 'Unknown',
            reason: t.reason_for_visit || t.reason || t.visit_reason || '',
            phone: t.phone || t.patient_phone || '',
            token: t.token_number || t.token || '',
            patientId: t.patient_id || t.mrn || '',
            tokenId: t.token_id || t.id || '',
            mrn: t.mrn || ''
          };
          this.isConsultationActive = true;
          if (!this.consultationStartTime) {
            this.consultationStartTime = new Date();
          }
        } else if (!this.isConsultationActive) {
          // No active consultation running — promote first upcoming as current
          if (rawUpcoming.length > 0) {
            const first = rawUpcoming[0];
            this.currentPatient = {
              name: first.name,
              age: first.age,
              gender: first.gender || 'Unknown',
              reason: first.reason,
              phone: first.phone || '',
              token: first.token,
              patientId: first.patientId,
              tokenId: first.tokenId,
              mrn: first.mrn || ''
            };
          } else {
            this.currentPatient = null;
          }
        }
        // If isConsultationActive but no current_consultation from backend yet,
        // keep the existing this.currentPatient untouched.

        // ─── STEP 3: Always filter serving token out of upcoming ──────────
        // Filter by BOTH tokenId and token string to handle any mapping gaps
        const servingTokenId = this.currentPatient?.tokenId;
        const servingToken = this.currentPatient?.token;

        this.upcomingPatients = rawUpcoming.filter(p =>
          (servingTokenId ? p.tokenId !== servingTokenId : true) &&
          (servingToken ? p.token !== servingToken : true)
        );

        console.log('[DASHBOARD] currentPatient:', this.currentPatient?.tokenId,
          '| upcoming count:', this.upcomingPatients.length);

        // ─── STEP 4: Skipped patients ──────────────────────────────────────
        if (d.skipped_patients && Array.isArray(d.skipped_patients)) {
          this.skippedPatients = d.skipped_patients.map((t: any) => ({
            token: t.token_number || t.token || '',
            name: t.patient_name || 'Unknown',
            age: this.parseAge(t.patient_age) || 0,
            reason: t.reason_for_visit || t.reason || '',
            waitTime: '0m',
            patientId: t.patient_id || t.mrn || '',
            tokenId: t.token_id || t.id || '',
            mrn: t.mrn || '',
            gender: t.patient_gender || 'Unknown',
            phone: t.phone || ''
          }));
        }

        // ─── STEP 5: Stats cards ───────────────────────────────────────────
        if (d.cards) {
          this.waitingPatients = d.cards.waiting_in_queue || 0;
          this.patientsServed = d.cards.patients_served || 0;
        }
      },
      error: (err) => {
        console.error('Error fetching doctor dashboard:', err);
        this.messageService.add({
          severity: 'warn',
          summary: 'Dashboard Error',
          detail: 'Could not load dashboard data. Retrying...'
        });
      }
    });
  }

  private parseAge(ageStr: any): number {
    if (!ageStr) return 0;
    if (typeof ageStr === 'number') return ageStr;
    const match = String(ageStr).match(/\d+/);
    return match ? parseInt(match[0], 10) : 0;
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/']);
  }

  viewPreviousHistory(): void {
    this.router.navigate(['/history']);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}