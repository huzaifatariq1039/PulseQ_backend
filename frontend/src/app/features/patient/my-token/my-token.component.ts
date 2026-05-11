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

  saveTicket(): void {
    this.messageService.add({
      severity: 'info',
      summary: 'Downloading',
      detail: 'Generating ticket...',
      life: 2000
    });

    setTimeout(() => {
      const W = 600, H = 980;
      const canvas = document.createElement('canvas');
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext('2d')!;

      const drawTicket = (logoImg: HTMLImageElement | null) => {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, W, H);

        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 2;
        ctx.strokeRect(18, 18, W - 36, H - 36);

        let y = 40;
        if (logoImg) {
          ctx.drawImage(logoImg, W / 2 - 36, y, 72, 72);
          y += 80;
        } else {
          y += 12;
        }

        ctx.fillStyle = '#000000';
        ctx.font = 'bold 17px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Rufayda Health Complex', W / 2, y);
        y += 18;

        ctx.font = '11px Arial';
        ctx.fillStyle = '#444444';
        ctx.fillText('Soan Gardens, Islamabad  |  +92 335 2015268', W / 2, y);
        y += 28;

        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(W - 36, y); ctx.stroke();
        y += 18;

        ctx.font = 'bold 11px Arial';
        ctx.fillStyle = '#000000';
        ctx.textAlign = 'center';
        ctx.fillText('QUEUE TICKET', W / 2, y);
        y += 28;

        ctx.font = 'bold 72px Arial';
        ctx.fillStyle = '#000000';
        ctx.textAlign = 'center';
        ctx.fillText(this.token?.tokenNumber || '-', W / 2, y + 60);
        y += 80;

        const status = (this.token?.status || 'pending').toUpperCase();
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

        ctx.strokeStyle = '#cccccc';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(W - 36, y); ctx.stroke();
        y += 20;

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

        drawSection('Appointment Info', y); y += 18;
        drawRow('Hospital', this.token?.hospital || '-', y, false); y += ROW_H;
        drawRow('Department', this.token?.department || '-', y, true); y += ROW_H;
        drawRow('Doctor', this.token?.doctor || 'Any', y, false); y += ROW_H;
        drawRow('Est. Wait Time', this.token?.estimatedWait || '-', y, true); y += ROW_H + 10;

        drawSection('Patient Details', y); y += 18;
        drawRow('Name', this.token?.patientName || '-', y, false); y += ROW_H;
        drawRow('MRN', this.token?.mrn || '-', y, true); y += ROW_H;
        drawRow('Phone', this.token?.patientPhone || '-', y, false); y += ROW_H;
        drawRow('Age', (this.token?.patientAge ?? '-') + ' years', y, true); y += ROW_H;
        drawRow('Gender', this.token?.patientGender || '-', y, false); y += ROW_H + 10;

        if (this.token?.specialNotes && this.token.specialNotes !== 'None') {
          drawSection('Notes', y); y += 18;
          ctx.font = '10px Arial';
          ctx.fillStyle = '#444444';
          ctx.textAlign = 'left';
          ctx.fillText(this.token.specialNotes.slice(0, 80), 48, y + 4);
          y += 22;
        }

        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(36, H - 56); ctx.lineTo(W - 36, H - 56); ctx.stroke();

        ctx.font = '10px Arial';
        ctx.fillStyle = '#777777';
        ctx.textAlign = 'center';
        ctx.fillText('Please keep this ticket safe.  For assistance, contact reception.', W / 2, H - 38);
        ctx.fillText('Rufayda Health Complex  -  Soan Gardens, Islamabad', W / 2, H - 22);

        canvas.toBlob((blob) => {
          if (!blob) return;
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `ticket-${this.token?.tokenNumber || 'ticket'}.png`;
          link.click();
          URL.revokeObjectURL(url);
          this.messageService.add({ severity: 'success', summary: 'Downloaded', detail: 'Ticket saved.', life: 3000 });
        });
      };

      const img = new Image();
      img.onload = () => drawTicket(img);
      img.onerror = () => drawTicket(null);
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