import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
import { TokenService } from '../../../core/services/token.service';
import { DoctorRating } from '../../../shared/models/doctor-rating.model';
import { RatingModalComponent } from '../../../shared/components/rating-modal/rating-modal.component';
import { StarRatingComponent } from '../../../shared/components/star-rating/star-rating.component';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { Subject } from 'rxjs';
import { ConsultationService } from '../../../core/services/consultation.service';

interface VisitDetail {
  id: string;
  doctor: string;
  specialty: string;
  doctorId: string;
  token: string;
  date: string;
  time: string;
  patientName: string;
  ageGender: string;
  phone: string;
  reason: string;
  notes: string;
  status: string;
  rating?: DoctorRating; // only this can be absent
}

@Component({
  selector: 'app-history-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    RatingModalComponent,
    StarRatingComponent,
    ToastModule,
    PatientHeaderComponent
  ],
  providers: [MessageService],
  templateUrl: './history-detail.component.html',
  styleUrl: './history-detail.component.css'
})
export class HistoryDetailComponent implements OnInit, OnDestroy {

  visit: VisitDetail | null = null;   // null (not undefined) works better with *ngIf as alias
  showRatingModal = false;
  loading = false;
  private destroy$ = new Subject<void>();

  constructor(
    private route: ActivatedRoute,
    private tokenService: TokenService,
    private consultationService: ConsultationService,
    private messageService: MessageService
  ) { }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    console.log('[History Detail] Loaded with ID:', id);
    if (!id) {
      console.error('[History Detail] No ID provided in route params');
      return;
    }

    this.loading = true;
    this.tokenService.getAppointmentDetails(id).subscribe({
      next: (res: any) => {
        this.loading = false;
        console.log('[History Detail] API Response:', res);

        // API returns: { token: {...}, doctor: {...}, hospital: {...}, queue: {...} }
        const data = res.token || res.appointment || res.data || res;
        if (data) {
          // Construct ageGender from separate fields
          const age = data.patient_age ?? data.patient?.age ?? 0;
          const gender = data.patient_gender ?? data.patient?.gender ?? 'Unknown';
          const ageGenderStr = age > 0 ? `${age}y • ${gender}` : gender;

          // Normalize rating from all possible API shapes
          let ratingObj: DoctorRating | undefined;
          const rawRating = data.rating ?? data.appointment_rating ?? data.doctor_rating ?? null;

          if (rawRating != null) {
            if (typeof rawRating === 'object') {
              const stars = rawRating.stars ?? rawRating.rating ?? rawRating.value ?? 0;
              if (stars > 0) {
                ratingObj = {
                  stars,
                  feedback: rawRating.feedback ?? rawRating.comments ?? undefined,
                  ratedAt: rawRating.ratedAt ?? rawRating.created_at ?? rawRating.date ?? new Date().toISOString()
                };
              }
            } else if (typeof rawRating === 'number' && rawRating > 0) {
              ratingObj = {
                stars: rawRating,
                ratedAt: new Date().toISOString()
              };
            }
          }

          // **FRONTEND FIX:** If no rating from backend, check localStorage cache
          // This works around the backend limitation where appointment-details doesn't include ratings
          if (!ratingObj) {
            const cachedRating = this.consultationService.getCachedRating(id);
            if (cachedRating) {
              ratingObj = cachedRating;
              console.log('[History Detail] Using cached rating for appointment', id, cachedRating);
            }
          }

          this.visit = {
            id: data.token_id || data.id || id,
            doctor: data.doctor_name || data.doctor || 'Any Doctor',
            doctorId: data.doctor_id || '',
            specialty: data.department || data.doctor_specialization || data.specialization || '—',
            token: data.display_code || data.token_number || '—',
            date: this.parseApiDate(data.appointment_date || data.start_time),
            time: this.parseApiTime(data.appointment_date || data.start_time),
            patientName: data.patient_name ?? data.patient?.name ?? '—',
            ageGender: ageGenderStr,
            phone: data.patient_phone ?? data.patient?.phone ?? '—',
            reason: data.reason_for_visit ?? data.chief_complaint ?? data.reason ?? '—',
            notes: data.notes ?? data.doctor_notes ?? data.consultation_notes ?? '—',
            status: data.status || 'completed',
            rating: ratingObj
          };

          console.log('APPOINTMENT DETAILS LOADED:', {
            visitId: this.visit.id,
            hasRating: !!ratingObj,
            ratingData: ratingObj,
            isEligible: this.visit.status.toLowerCase() === 'completed' && !ratingObj
          });
        }
      },
      error: (err) => {
        console.error('[History Detail] Failed to load appointment details:', err);
        this.loading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load appointment details. Please try again.'
        });
      }
    });
  }

  private parseApiDate(raw?: string): string {
    if (!raw) return '—';
    const parts = raw.split('-');
    if (parts.length === 3 && parts[0].length === 2) {
      const [d, m, y] = parts;
      const date = new Date(+y, +m - 1, +d);
      return isNaN(date.getTime()) ? raw : date.toDateString();
    }
    const parsed = new Date(raw);
    return isNaN(parsed.getTime()) ? raw : parsed.toDateString();
  }

  private parseApiTime(raw?: string): string {
    if (!raw) return 'Not specified';
    if (!raw.includes('T') && !raw.includes(' ')) return 'Not specified';
    const parsed = new Date(raw);
    return isNaN(parsed.getTime())
      ? 'Not specified'
      : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  openRatingModal(): void {
    this.showRatingModal = true;
  }

  onRatingSubmitted(rating: DoctorRating): void {
    if (!this.visit) return;

    // Ensure ratedAt is set
    if (!rating.ratedAt) {
      rating.ratedAt = new Date().toISOString();
    }

    // Cache the rating BEFORE sending to server to avoid data loss on network failure
    console.log('[History Detail] Caching rating before API call for visit:', this.visit.id);

    this.consultationService.submitRating(this.visit.id, rating).subscribe({
      next: () => {
        // Update local state immediately
        this.visit!.rating = { ...rating };

        // Also update via service for consistency
        this.consultationService.addRatingToConsultation(this.visit!.id, rating);

        console.log('RATING SUBMITTED SUCCESSFULLY:', {
          visitId: this.visit!.id,
          rating: this.visit!.rating,
          cached: true
        });

        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Thank you for your feedback!',
          life: 3000
        });

        this.showRatingModal = false;
      },
      error: (err) => {
        console.error('Failed to submit rating', err);

        // More detailed error handling
        let errorDetail = 'Failed to submit rating. Please try again.';
        if (err?.error?.message) {
          errorDetail = err.error.message;
        }

        // If rating is already cached, show a recovery message
        const cachedRating = this.consultationService.getCachedRating(this.visit!.id);
        if (cachedRating && err?.error?.message?.includes('already rated')) {
          console.log('[History Detail] Rating already exists (cache recovered)');
          this.visit!.rating = cachedRating;
          this.showRatingModal = false;
          this.messageService.add({
            severity: 'info',
            summary: 'Information',
            detail: 'Your rating has been saved.',
            life: 3000
          });
          return;
        }

        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: errorDetail
        });
      }
    });
  }

  isRatingEligible(): boolean {
    const isCompleted = this.visit?.status?.toLowerCase() === 'completed';
    const hasNoRating = !this.visit?.rating;

    // Debug log to track rating eligibility
    console.log('RATING ELIGIBILITY CHECK:', {
      status: this.visit?.status,
      isCompleted,
      hasRating: !!this.visit?.rating,
      hasNoRating,
      eligible: isCompleted && hasNoRating
    });

    return isCompleted && hasNoRating;
  }

  hasRating(): boolean {
    return !!this.visit?.rating;
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}