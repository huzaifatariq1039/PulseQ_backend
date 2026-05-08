import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
    selector: 'app-star-rating',
    standalone: true,
    imports: [CommonModule],
    template: `
    <div class="star-rating-container" [class.interactive]="interactive">
      <div class="stars">
        <button
          *ngFor="let star of starArray; let i = index"
          class="star"
          [class.filled]="star <= (hoverRating ?? selectedRating ?? 0)"
          [class.hover]="star <= (hoverRating ?? 0) && interactive"
          (click)="onStarClick(star)"
          (mouseenter)="interactive ? onStarHover(star) : null"
          (mouseleave)="onStarLeave()"
          [disabled]="!interactive"
          type="button"
          [attr.aria-label]="'Rate ' + star + ' stars'"
        >
          <i class="pi pi-star-fill"></i>
        </button>
      </div>
      <div *ngIf="interactive && hoverRating" class="rating-label">
        {{ getRatingLabel(hoverRating) }}
      </div>
      <div *ngIf="!interactive && selectedRating" class="rating-display">
        <span class="rating-value">{{ selectedRating }}.0</span>
      </div>
    </div>
  `,
    styleUrl: './star-rating.component.css',
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class StarRatingComponent {
    @Input() interactive: boolean = true;
    @Input() set rating(val: number | null | undefined) {
        if (val !== null && val !== undefined) {
            this.selectedRating = val;
        }
    }
    @Output() ratingSelected = new EventEmitter<number>();

    starArray = [1, 2, 3, 4, 5];
    selectedRating: number | null = null;
    hoverRating: number | null = null;

    onStarClick(star: number): void {
        if (!this.interactive) return;
        this.selectedRating = star;
        this.ratingSelected.emit(star);
    }

    onStarHover(star: number): void {
        if (!this.interactive) return;
        this.hoverRating = star;
    }

    onStarLeave(): void {
        this.hoverRating = null;
    }

    getRatingLabel(rating: number): string {
        const labels: { [key: number]: string } = {
            1: 'Poor',
            2: 'Fair',
            3: 'Good',
            4: 'Very Good',
            5: 'Excellent'
        };
        return labels[rating] || '';
    }
}
