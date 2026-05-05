import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { Router } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
import { TokenService, SmartTokenResponse } from '../../../core/services/token.service';
import { UserProfileService, UserProfile } from '../../../core/services/user-profile.service';
import { Subject, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface TokenStatus {
    token: SmartTokenResponse;
    currentServingToken: string;
    totalQueue: number;
    peopleAhead: number;
    queuePosition: number;
    estimatedWaitMinutes: number;
    expectedTime: string;
    isFutureAppointment: boolean;
    doctorUnavailable: boolean;
    progressPercentage: number;
    loading: boolean;
}

@Component({
    selector: 'app-live-status',
    standalone: true,
    imports: [CommonModule, CardModule, ButtonModule, PatientHeaderComponent],
    templateUrl: './live-status.component.html',
    styleUrl: './live-status.component.css'
})
export class LiveStatusComponent implements OnInit, OnDestroy {
    tokenStatuses: TokenStatus[] = [];
    selectedIndex = 0;
    hasToken = false;
    userProfile: UserProfile | null = null;

    private destroy$ = new Subject<void>();

    constructor(
        private tokenService: TokenService,
        private userProfileService: UserProfileService,
        private router: Router
    ) { }

    ngOnInit(): void {
        this.userProfileService.profile$
            .pipe(takeUntil(this.destroy$))
            .subscribe(profile => { this.userProfile = profile; });

        this.loadAllActiveTokens();
    }

    loadAllActiveTokens(): void {
        this.tokenService.getMyTokens(true)
            .pipe(takeUntil(this.destroy$))
            .subscribe({
                next: (tokens) => {
                    const activeTokens = (tokens as SmartTokenResponse[]).filter(
                        token => token.is_active === true
                    );

                    if (activeTokens && activeTokens.length > 0) {
                        this.hasToken = true;
                        this.tokenStatuses = activeTokens.map(token => ({

                            token,
                            currentServingToken: '-',
                            totalQueue: 0,
                            peopleAhead: 0,
                            queuePosition: 0,
                            estimatedWaitMinutes: 0,
                            expectedTime: '-',
                            isFutureAppointment: false,
                            doctorUnavailable: false,
                            progressPercentage: 0,
                            loading: true
                        }));

                        this.tokenStatuses.forEach((_, i) => this.fetchQueueStatus(i));

                        interval(30000)
                            .pipe(takeUntil(this.destroy$))
                            .subscribe(() => {
                                this.tokenStatuses.forEach((_, i) => this.fetchQueueStatus(i));
                            });
                    } else {
                        this.hasToken = false;
                    }
                },
                error: (err) => {
                    console.error('Failed to load active tokens', err);
                    this.hasToken = false;
                }
            });
    }

    fetchQueueStatus(index: number): void {
        const ts = this.tokenStatuses[index];
        if (!ts) return;
        this.tokenService.getTokenQueueStatus(ts.token.id).subscribe({
            next: (statusData) => {
                ts.loading = false;
                ts.currentServingToken = statusData.current_token_serving ?? statusData.current_token ?? statusData.currentToken ?? '-';
                ts.totalQueue = statusData.total_queue ?? statusData.totalQueue ?? 0;
                ts.peopleAhead = statusData.people_ahead ?? statusData.peopleAhead ?? 0;
                ts.queuePosition = statusData.queue_position ?? statusData.position ?? 0;
                ts.estimatedWaitMinutes = statusData.estimated_wait_time
                    ?? statusData.estimated_wait_minutes
                    ?? statusData.wait_time
                    ?? 0;
                ts.isFutureAppointment = statusData.is_future_appointment ?? false;
                ts.doctorUnavailable = statusData.doctor_unavailable ?? false;

                const originalPos = ts.token.queue_position ?? ts.queuePosition;
                ts.progressPercentage = originalPos > 0
                    ? Math.round(Math.max(0, Math.min(100, (1 - ts.queuePosition / originalPos) * 100)))
                    : 100;

                const now = new Date();
                now.setMinutes(now.getMinutes() + ts.estimatedWaitMinutes); // works even when 0
                ts.expectedTime = ts.estimatedWaitMinutes === 0
                    ? `Now (${now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })})`
                    : now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

            },
            error: (err) => console.error('Failed to fetch queue status for token', ts.token.id, err)
        });
    }

    get selected(): TokenStatus | null {
        return this.tokenStatuses[this.selectedIndex] ?? null;
    }

    selectTab(index: number): void {
        this.selectedIndex = index;
    }

    getTokenLabel(ts: TokenStatus): string {
        return ts.token.display_code ?? `Token ${ts.token.token_number}`;
    }

    public getDoctorInitials(name: string | undefined): string {
        if (!name) return 'DR';
        return name
            .split(' ')
            .filter(w => w.length > 0)
            .slice(0, 2)
            .map(w => w[0].toUpperCase())
            .join('');
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    goToGenerate(): void {
        this.router.navigate(['/new-token']);
    }

    openNotifications(): void {
        this.router.navigate(['/notifications']);
    }
}