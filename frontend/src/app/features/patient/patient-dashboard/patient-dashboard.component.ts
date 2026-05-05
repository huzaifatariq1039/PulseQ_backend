import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { QueueService } from '../../../core/services/queue.service';
import { TokenService } from '../../../core/services/token.service';
import { DashboardService } from '../../../core/services/dashboard.service';
import { UserProfileService, UserProfile } from '../../../core/services/user-profile.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

export interface ActiveToken {
  id: string;
  display_code: string;
  token_number: number;
  status: string;
  department: string;
  doctor_name: string;
  doctor_specialization: string;
  hospital_name: string;
  doctor_id: string;
  patient_name: string;
  payment_status: string;
  total_fee: number;
  reason_for_visit: string;
  appointment_date: string;
  queue_position: number | null;
  estimated_wait_time: number | null;
  current_token_serving: number | null;
  total_queue: number | null;
  people_ahead: number | null;
  is_future_appointment: boolean;
}

@Component({
  selector: 'app-patient-dashboard',
  standalone: true,
  imports: [CommonModule, CardModule, ButtonModule, PatientHeaderComponent],
  templateUrl: './patient-dashboard.component.html',
  styleUrls: ['./patient-dashboard.component.css']
})
export class PatientDashboardComponent implements OnInit, OnDestroy {
  patientName = 'Patient';
  userProfile: UserProfile | null = null;
  private destroy$ = new Subject<void>();

  activeTokens: ActiveToken[] = [];
  focusedTokenIndex = 0;
  hospitalUpdates = '';
  dashboardLoading = false;

  constructor(
    private router: Router,
    private queueService: QueueService,
    private tokenService: TokenService,
    private userProfileService: UserProfileService,
    private dashboardService: DashboardService
  ) { }

  // ── Computed ────────────────────────────────────────────────────
  get focusedToken(): ActiveToken | null {
    return this.activeTokens[this.focusedTokenIndex] ?? null;
  }

  // ── Pagination ──────────────────────────────────────────────────
  setFocusedToken(i: number): void { this.focusedTokenIndex = i; }
  prevToken(): void { if (this.focusedTokenIndex > 0) this.focusedTokenIndex--; }
  nextToken(): void {
    if (this.focusedTokenIndex < this.activeTokens.length - 1) this.focusedTokenIndex++;
  }

  // ── Lifecycle ───────────────────────────────────────────────────
  ngOnInit(): void {
    this.userProfileService.fetchProfile().pipe(takeUntil(this.destroy$)).subscribe();

    this.userProfileService.profile$.pipe(takeUntil(this.destroy$)).subscribe(profile => {
      this.userProfile = profile;
      if (profile?.fullName) {
        const first = profile.fullName.split(' ')[0];
        this.patientName = first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
      }
    });

    if (typeof window !== 'undefined') {
      this.dashboardLoading = true;

      // ── 1) Dashboard announcements
      this.dashboardService.getDashboardData().pipe(takeUntil(this.destroy$)).subscribe({
        next: (res: any) => {
          this.dashboardLoading = false;
          this.hospitalUpdates = res?.announcements || res?.hospital_updates || '';
        },
        error: () => { this.dashboardLoading = false; }
      });

      // ── 2) GET /patient/dashboard/active-token
      //    Always runs first and enriches token with real queue data
      this.dashboardService.getActiveToken().pipe(takeUntil(this.destroy$)).subscribe({
        next: (res: any) => {
          const token = res?.data?.token;
          const queue = res?.data?.queue;

          if (token && !['cancelled', 'completed'].includes(token.status) && !token.doctor_unavailable) {
            this.mergeToken({
              ...token,
              queue_position: queue?.queue_position ?? null,
              estimated_wait_time: queue?.estimated_wait_time ?? token.estimated_wait_time ?? null,
              current_token_serving: queue?.current_token_serving ?? null,
              total_queue: queue?.total_queue ?? null,
              people_ahead: queue?.people_ahead ?? null,
              is_future_appointment: queue?.is_future_appointment ?? false,
            });
          }
        },
        error: (err) => console.error('active-token error', err)
      });

      // ── 3) GET /patient/dashboard/recent-tokens?limit=20
      //    Only adds tokens NOT already enriched by the active-token call
      this.dashboardService.getRecentTokens(20).pipe(takeUntil(this.destroy$)).subscribe({
        next: (res: any) => {
          const tokens: any[] = Array.isArray(res?.data) ? res.data : [];
          tokens
            .filter(t =>
              !['cancelled', 'completed'].includes(t.status) &&
              !t.doctor_unavailable &&
              !this.activeTokens.find(existing => existing.id === t.id)  // ← don't overwrite queue-enriched tokens
            )
            .forEach(t => {
              const enrichedToken: ActiveToken = {
                ...t,
                queue_position: t.queue_position ?? null,
                estimated_wait_time: t.estimated_wait_time ?? null,
                current_token_serving: t.current_token_serving ?? null,
                total_queue: t.total_queue ?? null,
                people_ahead: null,
                is_future_appointment: false,
              };

              this.mergeToken(enrichedToken);

              //  If current_token_serving is missing, fetch queue status for this specific token
              if (enrichedToken.current_token_serving == null && enrichedToken.id) {
                this.tokenService.getTokenQueueStatus(enrichedToken.id).pipe(takeUntil(this.destroy$)).subscribe({
                  next: (queueData: any) => {
                    // Update the token with queue data
                    const idx = this.activeTokens.findIndex(existing => existing.id === enrichedToken.id);
                    if (idx !== -1) {
                      this.activeTokens[idx] = {
                        ...this.activeTokens[idx],
                        current_token_serving: queueData?.current_token_serving ?? queueData?.current_token ?? queueData?.currentToken ?? null,
                        queue_position: queueData?.queue_position ?? queueData?.position ?? null,
                        estimated_wait_time: queueData?.estimated_wait_time ?? queueData?.estimated_wait_minutes ?? queueData?.wait_time ?? null,
                        total_queue: queueData?.total_queue ?? queueData?.totalQueue ?? null,
                        people_ahead: queueData?.people_ahead ?? queueData?.peopleAhead ?? null
                      };
                      console.log(`[Patient Dashboard] Fetched queue status for token ${enrichedToken.id}:`, queueData);
                    }
                  },
                  error: (err) => console.error(`Failed to fetch queue status for token ${enrichedToken.id}:`, err)
                });
              }
            });
        },
        error: () => { }
      });
    }
  }

  /** Upsert without duplicates */
  private mergeToken(token: ActiveToken): void {
    const idx = this.activeTokens.findIndex(t => t.id === token.id);
    if (idx === -1) {
      this.activeTokens.push(token);
    } else {
      this.activeTokens[idx] = { ...this.activeTokens[idx], ...token };
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Navigation ──────────────────────────────────────────────────
  logout(): void { this.router.navigate(['/auth']); }
  goGenerateToken(): void { this.router.navigate(['/new-token']); }
  viewToken(): void { this.router.navigate(['/my-token']); }
  viewSpecificToken(id?: string): void {
    this.router.navigate(['/my-token'], id ? { queryParams: { id } } : {});
  }
  viewLiveStatus(): void { this.router.navigate(['/live-status']); }
  openNotifications(): void { this.router.navigate(['/notifications']); }

  // ── Helpers ─────────────────────────────────────────────────────
  getStatusLabel(status: string): string {
    const map: Record<string, string> = {
      pending: 'Waiting', called: 'Called',
      completed: 'Completed', cancelled: 'Cancelled',
      in_progress: 'In Progress', serving: 'Serving'
    };
    return map[status?.toLowerCase()] || status || '-';
  }

  getDotClass(status: string): string {
    const s = (status || '').toLowerCase();
    if (s === 'pending' || s === 'waiting') return 'dot-blue';
    if (s === 'called' || s === 'serving' || s === 'in_progress') return 'dot-green';
    if (s === 'cancelled') return 'dot-red';
    return 'dot-amber';
  }

  /** 
   * Display value for "Currently Serving".
   * Shows 0 when queue hasn't started yet — null means unknown (show dash).
   */
  getServingDisplay(token: ActiveToken): string {
    const n = token.current_token_serving;
    if (n == null) return '—';
    return String(n);  // 0 is valid — means no token called yet
  }

  /** Estimated wait — show "Now" if 0 or null */
  getWaitDisplay(token: ActiveToken): string {
    const w = token.estimated_wait_time;
    if (!w || w === 0) return 'Now';
    return `${w} min`;
  }

  /** Queue position — show 'Next' if position is 1 */
  getPositionDisplay(token: ActiveToken): string {
    const p = token.queue_position;
    if (p == null) return 'N/A';
    if (p === 1) return 'Next';
    return String(p);
  }
}