import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AuthService } from '../../../core/services/auth.service';
import { DoctorRating } from '../../../shared/models/doctor-rating.model';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DoctorSidebarComponent } from '../shared/components/doctor-sidebar/doctor-sidebar.component';

interface RatingCard {
    id: string;
    patientName: string;
    patientInitials: string;
    rating: DoctorRating;
    visitDate: Date;
    visitReason?: string;
    tokenNumber?: string;
}

interface RatingDistribution {
    stars: number;
    count: number;
    percentage: number;
}

@Component({
    selector: 'app-doctor-ratings',
    standalone: true,
    imports: [CommonModule, RouterModule, FormsModule, DoctorSidebarComponent],
    templateUrl: './doctor-ratings.component.html',
    styleUrl: './doctor-ratings.component.css'
})
export class DoctorRatingsComponent implements OnInit, OnDestroy {
    // sidebar state (mobile)
    sidebarOpen = false;

    // Data
    ratingCards: RatingCard[] = [];
    filteredRatings: RatingCard[] = [];

    // Calculations
    averageRating = 0;
    totalReviews = 0;
    distribution: RatingDistribution[] = [];

    // Filter & Sort State
    searchQuery = '';
    selectedStarFilter: number | null = null;
    sortBy: 'recent' | 'highest' | 'lowest' = 'recent';

    // UI State
    showEmptyState = false;
    showNoResults = false;

    // Math object for template
    Math = Math;

    private destroy$ = new Subject<void>();

    constructor(
        private staffService: StaffPortalService,
        private authService: AuthService,
        private route: ActivatedRoute,
        private router: Router
    ) {
        // Initialize distribution array
        this.distribution = [
            { stars: 5, count: 0, percentage: 0 },
            { stars: 4, count: 0, percentage: 0 },
            { stars: 3, count: 0, percentage: 0 },
            { stars: 2, count: 0, percentage: 0 },
            { stars: 1, count: 0, percentage: 0 }
        ];
    }

    ngOnInit(): void {
        this.loadRatings();
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }

    private loadRatings(): void {
        if (typeof window === 'undefined') return;

        const doctorId = this.authService.getCurrentUser()?.id;
        if (!doctorId) {
            console.error('No doctor ID found');
            this.showEmptyState = true;
            return;
        }

        this.staffService.getDoctorRatings(doctorId).subscribe({
            next: (res: any) => {
                if (res && Array.isArray(res.ratings)) {
                    this.ratingCards = res.ratings.map((r: any) => ({
                        id: r.id,
                        patientName: r.patient_name || r.patient_id || 'Unknown Patient',
                        patientInitials: this.getInitials(r.patient_name || r.patient_id || 'UP'),
                        rating: {
                            stars: r.rating,
                            feedback: r.review || 'No written feedback provided.',
                            ratedAt: r.created_at
                        },
                        visitDate: r.appointment_date || r.created_at,
                        visitReason: r.visit_reason || 'General checkup',
                        tokenNumber: r.token_id
                    }));

                    if (this.ratingCards.length === 0) {
                        this.showEmptyState = true;
                    } else {
                        this.showEmptyState = false;
                        this.calculateAverage();
                        this.calculateDistribution();
                        this.applyFiltersAndSort();
                    }
                } else {
                    this.showEmptyState = true;
                }
            },
            error: (err) => {
                console.error('Failed to load doctor ratings', err);
                this.showEmptyState = true;
            }
        });
    }
    private processRatings(): void {
        // Obsolete function since we map directly now
    }



    private calculateAverage(): void {
        if (this.ratingCards.length === 0) {
            this.averageRating = 0;
            this.totalReviews = 0;
            return;
        }

        const sum = this.ratingCards.reduce((acc, card) => acc + card.rating.stars, 0);
        this.averageRating = Math.round((sum / this.ratingCards.length) * 10) / 10;
        this.totalReviews = this.ratingCards.length;
    }

    private calculateDistribution(): void {
        // Reset counts
        this.distribution.forEach(d => d.count = 0);

        // Count ratings by stars
        this.ratingCards.forEach(card => {
            const dist = this.distribution.find(d => d.stars === card.rating.stars);
            if (dist) {
                dist.count++;
            }
        });

        // Calculate percentages
        if (this.ratingCards.length > 0) {
            this.distribution.forEach(d => {
                d.percentage = Math.round((d.count / this.ratingCards.length) * 100);
            });
        }
    }

    private getInitials(name: string): string {
        return name
            .split(' ')
            .map(part => part[0])
            .join('')
            .toUpperCase()
            .slice(0, 2);
    }

    onSearchChange(): void {
        this.applyFiltersAndSort();
    }

    onStarFilterChange(stars: number | null): void {
        this.selectedStarFilter = this.selectedStarFilter === stars ? null : stars;
        this.applyFiltersAndSort();
    }

    onFilterSelectChange(event: Event): void {
        const value = (event.target as HTMLSelectElement).value;
        this.onStarFilterChange(value === 'all' ? null : +value);
    }

    onSortChange(sortType: 'recent' | 'highest' | 'lowest'): void {
        this.sortBy = sortType;
        this.applyFiltersAndSort();
    }

    private applyFiltersAndSort(): void {
        let filtered = [...this.ratingCards];

        // Apply search filter
        if (this.searchQuery.trim()) {
            const query = this.searchQuery.toLowerCase();
            filtered = filtered.filter(card =>
                card.patientName.toLowerCase().includes(query) ||
                (card.rating.feedback?.toLowerCase().includes(query) ?? false)
            );
        }

        // Apply star filter
        if (this.selectedStarFilter !== null) {
            filtered = filtered.filter(card => card.rating.stars === this.selectedStarFilter);
        }

        // Apply sorting
        filtered.sort((a, b) => {
            switch (this.sortBy) {
                case 'recent':
                    return new Date(b.rating.ratedAt).getTime() - new Date(a.rating.ratedAt).getTime();
                case 'highest':
                    return b.rating.stars - a.rating.stars;
                case 'lowest':
                    return a.rating.stars - b.rating.stars;
                default:
                    return 0;
            }
        });

        this.filteredRatings = filtered;
        this.showNoResults = this.searchQuery.trim().length > 0 && filtered.length === 0;
    }

    getStarArray(count: number): number[] {
        return Array(5).fill(0).map((_, i) => i < count ? 1 : 0);
    }

    logout(): void {
        this.router.navigate(['../auth'], { relativeTo: this.route });
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }
}
