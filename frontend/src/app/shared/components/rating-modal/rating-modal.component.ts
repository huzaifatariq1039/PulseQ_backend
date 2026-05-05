import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { StarRatingComponent } from '../star-rating/star-rating.component';
import { DoctorRating } from '../../models/doctor-rating.model';

@Component({
    selector: 'app-rating-modal',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        DialogModule,
        ButtonModule,
        InputTextareaModule,
        StarRatingComponent
    ],
    template: `
    <p-dialog
      [(visible)]="visible"
      (onHide)="onCancel()"
      [modal]="true"
      [closable]="false"
      styleClass="rating-dialog"
      [style]="{ width: '100%', maxWidth: '500px' }"
      [baseZIndex]="10000"
    >
      <div class="rating-modal">
        <!-- Header -->
        <div class="modal-header">
          <button class="close-btn" (click)="onCancel()" type="button" aria-label="Close">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <!-- Content -->
        <div class="modal-content">
          <!-- Doctor Info -->
          <div class="doctor-info">
            <h2>Rate Your Experience</h2>
            <p class="doctor-name">{{ doctorName }} • {{ doctorSpecialty }}</p>
          </div>

          <!-- Star Rating -->
          <div class="star-section">
            <app-star-rating
              [interactive]="true"
              (ratingSelected)="onRatingSelected($event)"
            ></app-star-rating>
          </div>

          <!-- Feedback Textarea -->
          <form [formGroup]="feedbackForm">
            <div class="feedback-section">
              <label for="feedback" class="feedback-label">
                Write your feedback <span class="optional">(optional)</span>
              </label>
              <textarea
                id="feedback"
                formControlName="feedback"
                class="feedback-textarea"
                placeholder="Share your experience with the doctor..."
                maxlength="300"
              ></textarea>
              <div class="char-counter">
                {{ (feedbackForm.get('feedback')?.value || '').length }}/300
              </div>
            </div>
          </form>

          <!-- Buttons -->
          <div class="modal-footer">
            <button
              class="btn btn-cancel"
              (click)="onCancel()"
              pButton
              type="button"
              label="Cancel"
            ></button>
            <button
              class="btn btn-submit"
              (click)="onSubmit()"
              pButton
              type="button"
              label="Submit Rating"
              [disabled]="!selectedRating"
            ></button>
          </div>
        </div>
      </div>
    </p-dialog>
  `,
    styleUrl: './rating-modal.component.css',
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class RatingModalComponent {
    @Input() visible: boolean = false;
    @Input() doctorName: string = '';
    @Input() doctorSpecialty: string = '';
    @Output() visibleChange = new EventEmitter<boolean>();
    @Output() ratingSubmitted = new EventEmitter<DoctorRating>();

    feedbackForm: FormGroup;
    selectedRating: number | null = null;

    constructor(private fb: FormBuilder) {
        this.feedbackForm = this.fb.group({
            feedback: ['', [Validators.maxLength(300)]]
        });
    }

    onRatingSelected(rating: number): void {
        this.selectedRating = rating;
    }

    onSubmit(): void {
        if (!this.selectedRating) return;

        const rating: DoctorRating = {
            stars: this.selectedRating,
            feedback: this.feedbackForm.get('feedback')?.value || undefined,
            ratedAt: new Date().toISOString()
        };

        this.ratingSubmitted.emit(rating);
        this.resetForm();
        this.visibleChange.emit(false);
    }

    onCancel(): void {
        this.resetForm();
        this.visibleChange.emit(false);
    }

    private resetForm(): void {
        this.feedbackForm.reset();
        this.selectedRating = null;
    }
}
