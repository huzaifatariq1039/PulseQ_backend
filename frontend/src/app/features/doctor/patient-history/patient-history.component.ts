import { Component, OnInit, inject, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AuthService } from '../../../core/services/auth.service';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ScrollerModule } from 'primeng/scroller';
import { InputTextModule } from 'primeng/inputtext';
import { CalendarModule } from 'primeng/calendar';
import { DoctorSidebarComponent } from '../shared/components/doctor-sidebar/doctor-sidebar.component';
import { ConsultationService } from '../../../core/services/consultation.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, takeUntil } from 'rxjs';

interface PatientGroup {
  patientId: string;
  patientName: string;
  consultations: any[];
  isExpanded: boolean;
}

@Component({
  selector: 'app-doctor-patient-history',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterModule,
    ButtonModule, CardModule, ScrollerModule,
    InputTextModule, CalendarModule, DoctorSidebarComponent
  ],
  templateUrl: './patient-history.component.html',
  styleUrl: './patient-history.component.css'
})
export class PatientHistoryComponent implements OnInit {
  searchName: string = '';
  filterDate: Date | null = null;
  sidebarOpen = false;
  patientGroups: PatientGroup[] = [];
  filteredPatientId: string | null = null;

  private destroy$ = new Subject<void>();

  private staffService = inject(StaffPortalService);
  private consultationService = inject(ConsultationService);
  private authService = inject(AuthService);
  private activatedRoute = inject(ActivatedRoute);
  private router = inject(Router);

  ngOnInit(): void {
    this.activatedRoute.queryParams
      .pipe(takeUntil(this.destroy$))
      .subscribe(params => {
        this.filteredPatientId = params['patientId'] || null;
        this.loadConsultations();
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  private parseDate(dateStr: string | Date | null | undefined): Date {
    if (!dateStr) return new Date();
    if (dateStr instanceof Date) return dateStr;
    const parts = dateStr.split('-');
    if (parts.length === 3 && parts[0].length === 2) {
      return new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
    }
    return new Date(dateStr);
  }

  loadConsultations(): void {
    if (typeof window === 'undefined') return;

    if (this.filteredPatientId) {
      this.loadPatientHistory(this.filteredPatientId);
    } else {
      this.loadAllDoctorHistory();
    }
  }

  private loadPatientHistory(patientId: string): void {
    console.log('[PatientHistory] Fetching history for patientId:', patientId);

    this.staffService.getPatientConsultationHistory(patientId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          console.log('[PatientHistory] API response:', res);

          const patient = res?.data?.patient || {};
          const consultations = Array.isArray(res?.data?.history)
            ? res.data.history
            : [];

          const patientName = patient?.name
            || consultations[0]?.patient_name
            || consultations[0]?.patientName
            || patientId
            || 'Unknown';

          if (consultations.length === 0) {
            console.warn('[PatientHistory] history array is empty');
            this.patientGroups = [{
              patientId,
              patientName,
              consultations: [],
              isExpanded: true
            }];
            return;
          }

          const mapped = consultations.map((c: any) => ({
            tokenNumber: c.token_number || c.id || '#N/A',
            startTime: c.consultation_start_time || c.start_time || c.created_at,
            endTime: c.consultation_end_time || c.end_time || c.updated_at,
            reason: c.visit_reason || c.reason || '',
            doctorName: c.doctor_name || c.doctorName || 'Dr.',
            phone: patient?.phone || c.patient_phone || '',
            notes: c.consultation_notes || c.notes || c.special_instructions || '',
            patientName,
            duration: c.duration
          })).sort((a: any, b: any) =>
            this.parseDate(b.startTime).getTime() - this.parseDate(a.startTime).getTime()
          );

          this.patientGroups = [{
            patientId,
            patientName,
            consultations: mapped,
            isExpanded: true
          }];
        },
        error: (err) => {
          console.error('[PatientHistory] API error:', err);
          this.patientGroups = [];
        }
      });
  }

  private loadAllDoctorHistory(): void {
    console.log('[PatientHistory] No patientId — loading all doctor completed tokens');

    this.staffService.getDoctorTokens('completed', 1, 100)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          console.log('[PatientHistory] getDoctorTokens response:', res);

          if (!res.success || !Array.isArray(res.data)) {
            console.warn('[PatientHistory] Unexpected response shape', res);
            this.patientGroups = [];
            return;
          }

          const grouped = new Map<string, any[]>();

          res.data.forEach((t: any) => {
            const pid = t.mrn || t.patient_id || t.patient_phone || 'unknown';
            if (!grouped.has(pid)) grouped.set(pid, []);
            grouped.get(pid)!.push({
              tokenNumber: t.token_number,
              startTime: t.started_at || t.appointment_date,
              endTime: t.completed_at || t.appointment_date,
              reason: t.reason_for_visit || t.visit_reason || '',
              doctorName: t.doctor_name || 'Dr.',
              phone: t.patient_phone || '',
              notes: t.consultation_notes || t.notes || t.special_instructions || '',
              patientName: t.patient_name || 'Unknown',
              duration: t.duration
            });
          });

          const patientArray: PatientGroup[] = [];

          grouped.forEach((consultations, patientId) => {
            if (
              this.searchName &&
              !consultations[0].patientName
                .toLowerCase()
                .includes(this.searchName.toLowerCase())
            ) return;

            let filteredConsultations = consultations;
            if (this.filterDate) {
              const selectedDate = new Date(this.filterDate);
              filteredConsultations = consultations.filter(c => {
                const cDate = this.parseDate(c.startTime);
                return cDate.toDateString() === selectedDate.toDateString();
              });
            }

            const sortedConsultations = [...filteredConsultations].sort((a, b) =>
              this.parseDate(b.startTime).getTime() - this.parseDate(a.startTime).getTime()
            );

            if (sortedConsultations.length === 0) return;

            patientArray.push({
              patientId,
              patientName: consultations[0].patientName,
              consultations: sortedConsultations,
              isExpanded: false
            });
          });

          this.patientGroups = patientArray.sort((a, b) =>
            a.patientName.localeCompare(b.patientName)
          );
        },
        error: (err) => {
          console.error('[PatientHistory] getDoctorTokens error:', err);
          this.patientGroups = [];
        }
      });
  }

  togglePatientGroup(index: number): void {
    if (this.patientGroups[index]) {
      this.patientGroups[index].isExpanded = !this.patientGroups[index].isExpanded;
    }
  }

  formatDateTime(date: Date | string | null | undefined): string {
    if (!date) return 'N/A';
    const dateObj = this.parseDate(date as string);
    if (isNaN(dateObj.getTime())) return 'Invalid Date';
    return dateObj.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  calculateDuration(startTime: Date | string, endTime?: Date | string): number {
    const start = this.parseDate(startTime as string);
    if (!endTime) return 0;
    const end = this.parseDate(endTime as string);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) return 0;
    return Math.round((end.getTime() - start.getTime()) / 60000);
  }

  goBack(): void {
    this.router.navigate(['../dashboard'], { relativeTo: this.activatedRoute });
  }

  logout(): void {
    this.authService.logout();
  }
}