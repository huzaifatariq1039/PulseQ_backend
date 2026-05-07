import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { Consultation } from '../../../shared/models/consultation.model';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ScrollerModule } from 'primeng/scroller';
import { InputTextModule } from 'primeng/inputtext';
import { CalendarModule } from 'primeng/calendar';
import { DoctorSidebarComponent } from '../shared/components/doctor-sidebar/doctor-sidebar.component';
import { ConsultationService } from '../../../core/services/consultation.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

interface PatientGroup {
  patientId: string;
  patientName: string;
  consultations: any[];
  isExpanded: boolean;
}

@Component({
  selector: 'app-doctor-patient-history',
  standalone: true,
  imports: [CommonModule, FormsModule, ButtonModule, CardModule, ScrollerModule, InputTextModule, CalendarModule, DoctorSidebarComponent],
  templateUrl: './patient-history.component.html',
  styleUrl: './patient-history.component.css'
})
export class PatientHistoryComponent implements OnInit {
  searchName: string = '';
  filterDate: Date | null = null;
  // sidebar state for mobile
  sidebarOpen = false;

  patientGroups: PatientGroup[] = [];
  filteredPatientId: string | null = null;

  private staffService = inject(StaffPortalService);
  private consultationService = inject(ConsultationService);
  private activatedRoute = inject(ActivatedRoute);
  private router = inject(Router);

  ngOnInit(): void {
    //filter by specific patient
    this.activatedRoute.queryParams
      .pipe(takeUntilDestroyed())
      .subscribe(params => {
        this.filteredPatientId = params['patientId'] || null;
        this.loadConsultations();
      });
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  /**
   * Parses date strings in both DD-MM-YYYY and ISO/standard formats.
   * The API returns dates like "27-04-2026" which new Date() cannot parse correctly.
   */
  private parseDate(dateStr: string | Date | null | undefined): Date {
    if (!dateStr) return new Date();
    if (dateStr instanceof Date) return dateStr;

    // Handle DD-MM-YYYY format (e.g. "27-04-2026")
    const parts = dateStr.split('-');
    if (parts.length === 3 && parts[0].length === 2) {
      // Rearrange to YYYY-MM-DD so JS can parse it
      return new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
    }

    // Fallback for ISO strings or other standard formats
    return new Date(dateStr);
  }

  loadConsultations(): void {
    if (typeof window === 'undefined') return;

    if (this.filteredPatientId) {
      this.consultationService.getPatientHistoryApi(this.filteredPatientId)
        .pipe(takeUntilDestroyed())
        .subscribe({
          next: (res: any) => {
            if (res && res.data) {
              const consultations = Array.isArray(res.data) ? res.data : [res.data];
              const patientName = consultations.length > 0
                ? (consultations[0].patient_name || consultations[0].patient_id || 'Unknown')
                : 'Unknown';

              const mapped = consultations.map((t: any) => ({
                tokenNumber: t.token_number || t.id,
                startTime: t.created_at || t.start_time,
                endTime: t.updated_at || t.end_time,
                reason: t.visit_reason || t.reason || '',
                doctorName: t.doctor_name || 'Dr.',
                phone: t.patient_phone || '',
                notes: t.consultation_notes || t.notes || t.special_instructions || '',
                patientName: t.patient_name || t.patient_id || 'Unknown'
              })).sort((a: any, b: any) =>
                this.parseDate(b.startTime).getTime() - this.parseDate(a.startTime).getTime()
              );

              this.patientGroups = [{
                patientId: this.filteredPatientId!,
                patientName,
                consultations: mapped,
                isExpanded: true
              }];
            }
          },
          error: (err) => console.error('Failed to load specific patient history', err)
        });
      return;
    }
    this.staffService.getDoctorTokens('completed', 1, 100)
      .pipe(takeUntilDestroyed())
      .subscribe({
      next: (res: any) => {
        if (res.success && Array.isArray(res.data)) {
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
            // Filter by search name
            if (this.searchName && !consultations[0].patientName.toLowerCase().includes(this.searchName.toLowerCase())) {
              return;
            }

            // Filter by date — use parseDate to correctly handle DD-MM-YYYY
            let filteredConsultations = consultations;
            if (this.filterDate) {
              const selectedDate = new Date(this.filterDate);
              filteredConsultations = consultations.filter(c => {
                const cDate = this.parseDate(c.startTime);
                return cDate.toDateString() === selectedDate.toDateString();
              });
            }

            // Sort descending by startTime — use parseDate to avoid Invalid Date
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

          this.patientGroups = patientArray.sort((a, b) => a.patientName.localeCompare(b.patientName));
        }
      },
      error: (err) => console.error('Failed to load history', err)
    });
  }

  togglePatientGroup(index: number): void {
    if (this.patientGroups[index]) {
      this.patientGroups[index].isExpanded = !this.patientGroups[index].isExpanded;
    }
  }

  formatDateTime(date: Date | string | null | undefined): string {
    if (!date) return 'N/A';
    // Use parseDate to handle DD-MM-YYYY from API
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
    this.router.navigate(['../auth'], { relativeTo: this.activatedRoute });
  }
}