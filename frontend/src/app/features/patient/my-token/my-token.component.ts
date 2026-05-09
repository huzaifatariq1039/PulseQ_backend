import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageService, ConfirmationService } from 'primeng/api';
import { TokenService } from '../../../core/services/token.service';
import { NotificationService } from '../../../core/services/notification.service';
import { UserProfileService, UserProfile } from '../../../core/services/user-profile.service';
import { RealtimeService } from '../../../core/services/realtime.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface MappedToken {
  id: string;
  tokenNumber: string;
  hospital: string;
  department: string;
  doctor: string;
  patientName: string;
  patientPhone: string;
  mrn: string;
  patientAge: string | number;
  patientGender: string;
  specialNotes: string;
  reasonForVisit: string;
  status: string;
  estimatedWait: string;
  queuePosition: number | string;
  peopleAhead: number | string;
  totalQueue: number | string;
}

@Component({
  selector: 'app-my-token',
  standalone: true,
  imports: [
    CommonModule,
    ButtonModule,
    CardModule,
    ToastModule,
    ConfirmDialogModule,
    PatientHeaderComponent
  ],
  providers: [MessageService, ConfirmationService],
  templateUrl: './my-token.component.html',
  styleUrl: './my-token.component.css'
})
export class MyTokenComponent implements OnInit, OnDestroy {
  /** All active tokens the patient has */
  allTokens: MappedToken[] = [];

  /** Index of the currently selected token tab */
  selectedTokenIndex = 0;

  /** Convenience getter: currently displayed token */
  get token(): MappedToken | null {
    return this.allTokens[this.selectedTokenIndex] ?? null;
  }

  get hasActiveToken(): boolean {
    return this.allTokens.length > 0;
  }

  userProfile: UserProfile | null = null;
  private destroy$ = new Subject<void>();
  private realtimeConnected = false;
  private currentDoctorId: string | null = null;

  constructor(
    private messageService: MessageService,
    private confirmationService: ConfirmationService,
    private router: Router,
    private route: ActivatedRoute,
    private tokenService: TokenService,
    private userProfileService: UserProfileService,
    private notificationService: NotificationService,
    private realtimeService: RealtimeService
  ) { }

  ngOnInit(): void {
    this.userProfileService.profile$
      .pipe(takeUntil(this.destroy$))
      .subscribe(profile => { this.userProfile = profile; });

    // Step 1: Load ALL active tokens first (for the pill tabs)
    this.tokenService.getMyTokens(true)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          // API returns array directly OR wrapped in data
          const tokens: any[] = Array.isArray(res) ? res : (Array.isArray(res?.data) ? res.data : []);
          const invalid = ['cancelled', 'completed'];
          tokens
            .filter(t => !invalid.includes(t.status))
            .forEach(t => this.mergeToken(this.mapToken(t, null)));

          // Step 2: Load active-details for the FIRST token's queue data
          this.loadActiveTokenDetails();
        },
        error: () => {
          // Fallback: just load the single active token
          this.loadActiveTokenDetails();
        }
      });

    // Handle query param: if navigated from dashboard with ?id=
    this.route.queryParams
      .pipe(takeUntil(this.destroy$))
      .subscribe(params => {
        if (params['id']) {
          // Wait a tick for allTokens to populate
          setTimeout(() => {
            const idx = this.allTokens.findIndex(t => t.id === params['id']);
            if (idx >= 0) this.selectedTokenIndex = idx;
          }, 500);
        }
      });
  }

  private loadActiveTokenDetails(): void {
    this.tokenService.getMyActiveTokenDetails()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          // Handle both array response and single object response
          const detailsArray = Array.isArray(res) ? res : (res && res.token ? [res] : []);

          detailsArray.forEach((item: any) => {
            const token = item.token || item;
            const queue = item.queue || null;

            if (token) {
              const mapped = this.mapToken(token, queue);
              this.mergeToken(mapped);

              // Setup WebSocket for the first token's doctor
              const doctorId = token.doctor_id;
              if (doctorId && doctorId !== this.currentDoctorId) {
                this.setupRealtimeListener(doctorId);
              }
            }
          });
        },
        error: (err) => {
          console.error('Failed to get active token details', err);
        }
      });
  }

  private setupRealtimeListener(doctorId: string): void {
    if (this.realtimeConnected && this.currentDoctorId === doctorId) return;

    // Clean up old connection if switching doctors
    if (this.currentDoctorId && this.currentDoctorId !== doctorId) {
      this.realtimeService.disconnect(`doctor_${this.currentDoctorId}`);
    }

    this.currentDoctorId = doctorId;
    const room = `doctor_${doctorId}`;

    this.realtimeService.connect(room)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (message: any) => {
          if (message && ['QUEUE_UPDATE', 'TOKEN_UPDATE'].includes(message.type)) {
            this.loadActiveTokenDetails();
          }
        },
        error: (err) => {
          console.error(`WebSocket error for room ${room}:`, err);
        }
      });

    this.realtimeConnected = true;
  }


  private mapToken(apiToken: any, queue: any): MappedToken {
    return {
      id: apiToken.id,
      tokenNumber: apiToken.display_code || apiToken.token_number?.toString() || '-',
      hospital: apiToken.hospital_name || '-',
      department: apiToken.department || '-',
      doctor: apiToken.doctor_name || 'Any',
      patientName: apiToken.patient_name || apiToken.patient?.name || '-',
      patientPhone: apiToken.patient_phone || apiToken.patient?.phone || '-',
      mrn: apiToken.mrn || '-',
      patientAge: apiToken.patient_age ?? apiToken.patient?.age ?? '-',
      patientGender: apiToken.patient_gender ?? apiToken.patient?.gender ?? '-',
      specialNotes: apiToken.notes || apiToken.special_notes || 'None',
      reasonForVisit: apiToken.reason_for_visit || '-',
      status: apiToken.status || 'waiting',
      estimatedWait: (queue?.estimated_wait_time != null)
        ? (queue.estimated_wait_time === 0 ? 'Now' : `${queue.estimated_wait_time} min`)
        : (apiToken.estimated_wait_time != null
          ? (apiToken.estimated_wait_time === 0 ? 'Now' : `${apiToken.estimated_wait_time} min`)
          : '-'),
      queuePosition: queue?.queue_position ?? '-',
      peopleAhead: queue?.people_ahead ?? '-',
      totalQueue: queue?.total_queue ?? '-'
    };
  }

  private mergeToken(mapped: MappedToken): void {
    const idx = this.allTokens.findIndex(t => t.id === mapped.id);
    if (idx < 0) {
      this.allTokens.push(mapped);
    } else {
      this.allTokens[idx] = mapped;
    }
  }

  selectToken(index: number): void {
    this.selectedTokenIndex = index;
  }

  ngOnDestroy(): void {
    if (this.realtimeConnected && this.currentDoctorId) {
      this.realtimeService.disconnect(`doctor_${this.currentDoctorId}`);
    }
    this.destroy$.next();
    this.destroy$.complete();
  }

  saveTicket(): void {
    this.messageService.add({
      severity: 'info',
      summary: 'Downloading',
      detail: 'Downloading ticket as image...',
      life: 2000
    });

    setTimeout(() => {
      const canvas = document.createElement('canvas');
      canvas.width = 500;
      canvas.height = 640;
      const ctx = canvas.getContext('2d');

      if (ctx) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#2563eb';
        ctx.fillRect(0, 0, canvas.width, 8);

        ctx.fillStyle = '#000000';
        ctx.font = 'bold 72px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(this.token?.tokenNumber || '', canvas.width / 2, 120);

        ctx.font = '14px Arial';
        ctx.fillStyle = '#666666';
        ctx.textAlign = 'center';
        let yPos = 170;
        const lineHeight = 22;

        const t = this.token;
        ctx.fillText(`Hospital: ${t?.hospital}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Department: ${t?.department}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Doctor: ${t?.doctor || 'Any'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Name: ${t?.patientName || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Phone: ${t?.patientPhone || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`MRN: ${t?.mrn || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Age: ${t?.patientAge || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Gender: ${t?.patientGender || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Queue Position: ${t?.queuePosition || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`People Ahead: ${t?.peopleAhead ?? '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        if (t?.specialNotes && t.specialNotes !== 'None') {
          ctx.fillText(`Notes: ${t?.specialNotes}`, canvas.width / 2, yPos); yPos += lineHeight;
        }
        ctx.fillText(`Estimated Wait: ${t?.estimatedWait || '-'}`, canvas.width / 2, yPos); yPos += lineHeight;
        ctx.fillText(`Status: ${t?.status?.toUpperCase() || '-'}`, canvas.width / 2, yPos);
      }

      canvas.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `ticket-${this.token?.tokenNumber}.png`;
          link.click();
          URL.revokeObjectURL(url);
        }
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Ticket downloaded as image',
          life: 3000
        });
      });
    }, 1500);
  }

  leaveQueue(): void {
    if (!this.token?.id) return;
    this.confirmationService.confirm({
      message: 'Are you sure you want to cancel your token? This action cannot be undone.',
      header: 'Cancel Token',
      icon: 'pi pi-exclamation-triangle',
      accept: () => {
        this.tokenService.cancelTokenAlias({ token_id: this.token!.id }).subscribe({
          next: () => {
            const tokenCode = this.token?.tokenNumber || 'N/A';
            // Remove from allTokens array
            this.allTokens = this.allTokens.filter(t => t.id !== this.token!.id);
            // Reset selected index
            this.selectedTokenIndex = Math.max(0, this.selectedTokenIndex - 1);

            this.notificationService.sendTokenCancelled(tokenCode);
            this.messageService.add({
              severity: 'warn',
              summary: 'Queue Left',
              detail: 'You have cancelled your token.',
              life: 3000
            });
          },
          error: (err) => {
            console.error('Failed to cancel token', err);
            this.messageService.add({
              severity: 'error',
              summary: 'Error',
              detail: 'Failed to cancel token. Please try again later.',
              life: 3000
            });
          }
        });
      },
      reject: () => {
        this.messageService.add({
          severity: 'info',
          summary: 'Not Cancelled',
          detail: 'Your token is still active.',
          life: 2000
        });
      }
    });
  }

  generateToken(): void {
    this.router.navigate(['../new-token'], { relativeTo: this.route });
  }

  openNotifications(): void {
    this.router.navigate(['../notifications'], { relativeTo: this.route });
  }
}