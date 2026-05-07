import { Component, OnInit, inject } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { ConsultationService } from '../../../core/services/consultation.service';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';
import { Consultation } from '../../../shared/models/consultation.model';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CardModule } from 'primeng/card';
import { TableModule } from 'primeng/table';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { RippleModule } from 'primeng/ripple';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

export interface CompletedToken {
    id: string;
    tokenNumber: string;
    patientName: string;
    mrn?: string;
    age?: number;
    gender?: string;
    phone?: string;
    cnic?: string;
    visitReason?: string;
    department?: string;
    doctorName?: string;
    createdAt?: Date;
    consultationStartTime?: Date;
    consultationEndTime?: Date;
    consultationNotes?: string;
    status: 'pending' | 'in-progress' | 'completed';
    apiDuration?: number;
}

@Component({
    selector: 'app-completed-consultations',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        RouterModule,
        AdminSidebarComponent,
        CardModule,
        TableModule,
        DialogModule,
        ButtonModule,
        ToastModule,
        RippleModule
    ],
    templateUrl: './completed-consultations.component.html',
    styleUrls: ['./completed-consultations.component.css']
})
export class CompletedConsultationsComponent implements OnInit {
    tokens: CompletedToken[] = [];
    selectedToken: CompletedToken | null = null;
    displayDialog: boolean = false;

    completedToday = 0;
    averageDuration = 0;
    completedThisMonth = 0;

    private consultationService = inject(ConsultationService);
    private staffService = inject(StaffPortalService);
    private router = inject(Router);

    ngOnInit(): void {
        this.loadFromApi();
    }

    private loadFromApi(): void {
        this.staffService.getCompletedTokens(1, 100)
            .pipe(takeUntilDestroyed())
            .subscribe({
                next: (res: any) => {
                    const raw: any[] = Array.isArray(res)
                        ? res
                        : Array.isArray(res?.data)
                            ? res.data
                            : [];

                    this.tokens = raw.map((t: any) => this.mapApiTokenToCompletedToken(t));

                    if (res?.meta) {
                        this.completedToday = res.meta.completed_today ?? 0;
                        this.completedThisMonth = res.meta.completed_this_month ?? 0;
                        this.averageDuration = res.meta.avg_consultation_time ?? 0;
                    } else {
                        this.computeMetrics();
                    }
                },
                error: (err) => {
                    console.error('Failed to load completed consultations from API, falling back to local', err);
                    this.loadFromLocal();
                }
            });
    }

    private loadFromLocal(): void {
        this.consultationService.consultations$
            .pipe(takeUntilDestroyed())
            .subscribe(list => {
                this.tokens = list
                    .filter(c => !!c.endTime)
                    .map(c => this.mapConsultationToToken(c));
                this.computeMetrics();
            });
    }

    private computeMetrics(): void {
        const now = new Date();
        this.completedToday = this.getCompletedCountOnDate(now);
        this.completedThisMonth = this.getCompletedCountInMonth(now);

        const durations = this.tokens
            .filter(t => t.apiDuration !== undefined && t.apiDuration > 0)
            .map(t => t.apiDuration as number);

        this.averageDuration = durations.length > 0
            ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
            : 0;
    }

    openDetails(token: CompletedToken): void {
        this.selectedToken = token;
        this.displayDialog = true;
    }

    closeDialog(): void {
        this.displayDialog = false;
        this.selectedToken = null;
    }

    getDuration(token: CompletedToken): number {
        if (token.apiDuration !== undefined) {
            return token.apiDuration;
        }
        if (!token.consultationStartTime || !token.consultationEndTime) return 0;
        const start = new Date(token.consultationStartTime).getTime();
        const end = new Date(token.consultationEndTime).getTime();
        return Math.floor((end - start) / 60000);
    }

    private parseDMY(val: string): Date | undefined {
        if (!val) return undefined;
        const parts = val.split('-');
        if (parts.length !== 3) return undefined;
        const d = new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
        return isNaN(d.getTime()) ? undefined : d;
    }

    private mapApiTokenToCompletedToken(t: any): CompletedToken {
        const pick = (...keys: string[]): any =>
            keys.reduce((acc: any, k: string) => {
                if (acc !== undefined && acc !== null) return acc;
                const val = t[k];
                return (val !== undefined && val !== null) ? val : undefined;
            }, undefined);

        const parseDate = (...keys: string[]): Date | undefined => {
            const val = keys.reduce((acc: any, k: string) => acc ?? t[k], undefined);
            if (!val) return undefined;
            const fromDMY = this.parseDMY(val);
            if (fromDMY) return fromDMY;
            const d = new Date(val);
            return isNaN(d.getTime()) ? undefined : d;
        };

        return {
            id: pick('id', 'token_id', 'tokenId') ?? '',
            tokenNumber: String(pick('token_number', 'tokenNumber') ?? ''),
            patientName: pick('patient_name', 'patientName') ?? '',
            mrn: pick('mrn', 'MRN') ?? '',
            age: pick('patient_age', 'patientAge', 'age'),
            gender: pick('patient_gender', 'patientGender', 'gender') ?? '',
            phone: pick('patient_phone', 'patientPhone', 'phone') ?? '',
            cnic: pick('patient_cnic', 'patientCnic', 'cnic') ?? '',
            visitReason: pick('visit_reason', 'visitReason', 'reason') ?? '',
            department: pick('department') ?? '',
            doctorName: pick('doctor_name', 'doctorName') ?? '',
            createdAt: parseDate('created_at', 'createdAt'),
            consultationStartTime: parseDate('consultation_start_time', 'consultationStartTime', 'start_time', 'startTime'),
            consultationEndTime: parseDate('consultation_end_time', 'consultationEndTime', 'end_time', 'endTime'),
            consultationNotes: pick('notes', 'consultation_notes', 'consultationNotes', 'special_instructions') ?? '',
            status: 'completed',
            apiDuration: t.duration ?? 0
        };
    }

    private mapConsultationToToken(c: Consultation): CompletedToken {
        return {
            id: c.id,
            tokenNumber: c.tokenNumber ?? '',
            mrn: (c as any).patientMRN ?? '',
            patientName: c.patientName ?? '',
            age: (c as any).patientAge,
            gender: (c as any).patientGender,
            phone: c.phone,
            cnic: (c as any).patientCNIC,
            visitReason: c.reason,
            department: (c as any).department,
            doctorName: c.doctorName ?? '',
            createdAt: (c as any).createdAt,
            consultationStartTime: c.startTime,
            consultationEndTime: c.endTime,
            consultationNotes: c.notes,
            status: 'completed',
            apiDuration: undefined
        };
    }

    private getCompletedCountOnDate(date: Date): number {
        return this.tokens.filter(t => {
            if (!t.consultationEndTime) return false;
            const d = new Date(t.consultationEndTime);
            return (
                d.getFullYear() === date.getFullYear() &&
                d.getMonth() === date.getMonth() &&
                d.getDate() === date.getDate()
            );
        }).length;
    }

    private getCompletedCountInMonth(date: Date): number {
        return this.tokens.filter(t => {
            if (!t.consultationEndTime) return false;
            const d = new Date(t.consultationEndTime);
            return (
                d.getFullYear() === date.getFullYear() &&
                d.getMonth() === date.getMonth()
            );
        }).length;
    }
}