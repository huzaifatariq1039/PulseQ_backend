import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { NotificationService } from '../../../../../core/services/notification.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
    selector: 'app-patient-header',
    standalone: true,
    imports: [CommonModule, RouterLink, RouterLinkActive, ButtonModule],
    templateUrl: './patient-header.component.html',
    styleUrls: ['./patient-header.component.css']
})
export class PatientHeaderComponent implements OnInit, OnDestroy {
    mobileMenuOpen = false;
    unreadCount = 0;
    private destroy$ = new Subject<void>();

    constructor(private notificationService: NotificationService) { }

    ngOnInit(): void {
        this.notificationService.notifications$
            .pipe(takeUntil(this.destroy$))
            .subscribe(() => {
                this.unreadCount = this.notificationService.getUnreadCount();
            });
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    toggleMenu(): void {
        this.mobileMenuOpen = !this.mobileMenuOpen;
    }
}