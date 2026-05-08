import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
import { PatientActionsService } from '../../../core/services/patient-actions.service';
import { StarRatingComponent } from '../../../shared/components/star-rating/star-rating.component';
import { ConsultationService } from '../../../core/services/consultation.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface Visit {
  id: string;
  doctor: string;
  specialty?: string;
  date: string;
  time: string;
  reason?: string;
  token?: string;
  status?: string;
  hasNotes: boolean;
  hasRated: boolean;
  rating?: { stars: number; feedback?: string };
}

@Component({
  selector: 'app-patient-history',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, StarRatingComponent, PatientHeaderComponent],
  templateUrl: './patient-history.component.html',
  styleUrl: './patient-history.component.css'
})
export class PatientHistoryComponent implements OnInit, OnDestroy {
  visits: Visit[] = [];
  loading = true;
  completedCount = 0;
  searchTerm = '';
  doctorNameFilter = '';
  dateFilter = '';
  private destroy$ = new Subject<void>();

  constructor(
    private patientActionsService: PatientActionsService,
    private consultationService: ConsultationService
  ) { }

  ngOnInit(): void {
    this.loading = true;
    this.patientActionsService.getVisitHistory()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res: any) => {
          this.loading = false;
          const data = Array.isArray(res)
            ? res
            : (res?.data?.visits || res?.visits || res?.data || []);

          console.log('RAW VISIT DATA (first item):', data[0]);

          this.visits = data.map((v: any) => {
            // Normalize rating from all possible API shapes
            const rawRating =
              v.rating ??
              v.appointment_rating ??
              v.doctor_rating ??
              v.visit_rating ??
              null;

            let ratingObj: { stars: number; feedback?: string; ratedAt?: string } | undefined;

            if (rawRating != null) {
              if (typeof rawRating === 'object') {
                const stars = rawRating.stars ?? rawRating.rating ?? rawRating.value ?? 0;
                if (stars > 0) {
                  ratingObj = {
                    stars,
                    feedback: rawRating.feedback ?? rawRating.comments,
                    ratedAt: rawRating.ratedAt ?? rawRating.created_at ?? rawRating.date
                  };
                }
              } else if (typeof rawRating === 'number' && rawRating > 0) {
                ratingObj = { stars: rawRating };
              }
            }

            // **FRONTEND FIX:** If no rating from backend, check localStorage cache
            // This works around the backend limitation where visit-history doesn't always include ratings
            const appointmentId = v.id || v.token_id || '';
            if (!ratingObj && appointmentId) {
              const cachedRating = this.consultationService.getCachedRating(appointmentId);
              if (cachedRating) {
                ratingObj = cachedRating;
                console.log('[Patient History] Using cached rating for visit', appointmentId, cachedRating);
              }
            }

            return {
              id: v.id || v.token_id || '',
              doctor: v.doctor_name || v.doctor || '-',
              specialty: v.specialization || v.department || '',
              date: this.parseDate(
                v.start_time || v.end_time || v.visit_date ||
                v.appointment_date || v.created_at || ''
              ),
              time: v.visit_time || '',
              reason: v.visit_reason || v.reason || '',
              token: v.token_number || '',
              status: v.status || 'completed',
              hasNotes: !!(v.notes || v.has_notes),
              hasRated: ratingObj !== undefined, // ← derives from actual rating data
              rating: ratingObj
            };
          });

          this.completedCount = this.visits.filter(v => v.status === 'completed').length;
        },
        error: (err) => {
          this.loading = false;
          console.error('Failed to fetch visit history', err);
          this.visits = [];
          this.completedCount = 0;
        }
      });
  }

  parseDate(raw: string): string {
    if (!raw) return '';
    // Convert DD-MM-YYYY → YYYY-MM-DD for Angular date pipe
    const match = raw.match(/^(\d{2})-(\d{2})-(\d{4})$/);
    if (match) return `${match[3]}-${match[2]}-${match[1]}`;
    return raw;
  }

  getInitial(doctorName: string): string {
    const cleaned = doctorName.replace(/^Dr\.?\s*/i, '');
    return cleaned.charAt(0).toUpperCase() || 'D';
  }

  get filteredVisits(): Visit[] {
    return this.visits.filter(visit => {
      // Search by doctor name or specialty
      const doctorMatch = !this.doctorNameFilter ||
        visit.doctor.toLowerCase().includes(this.doctorNameFilter.toLowerCase()) ||
        (visit.specialty && visit.specialty.toLowerCase().includes(this.doctorNameFilter.toLowerCase()));

      // Search by reason or token (patient-related search)
      const searchMatch = !this.searchTerm ||
        (visit.reason && visit.reason.toLowerCase().includes(this.searchTerm.toLowerCase())) ||
        (visit.token && visit.token.toString().includes(this.searchTerm)) ||
        visit.doctor.toLowerCase().includes(this.searchTerm.toLowerCase());

      // Filter by date
      let dateMatch = true;
      if (this.dateFilter) {
        const filterDate = new Date(this.dateFilter);
        const visitDate = new Date(visit.date);
        dateMatch = visitDate.toDateString() === filterDate.toDateString();
      }

      return doctorMatch && searchMatch && dateMatch;
    });
  }

  clearFilters(): void {
    this.searchTerm = '';
    this.doctorNameFilter = '';
    this.dateFilter = '';
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}