import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputSwitchModule } from 'primeng/inputswitch';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { NotificationService, Notification } from '../../../core/services/notification.service';

@Component({
    selector: 'app-patient-notification',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterModule, CardModule, ButtonModule, InputSwitchModule, PatientHeaderComponent],
    templateUrl: './patient-notification.component.html',
    styleUrls: ['./patient-notification.component.css']
})
export class PatientNotificationComponent implements OnInit, OnDestroy {
    activeTab: 'inbox' | 'settings' = 'inbox';
    notifications: Notification[] = [];
    private destroy$ = new Subject<void>();

    constructor(private notificationService: NotificationService) { }

    ngOnInit(): void {
        this.notificationService.notifications$
            .pipe(takeUntil(this.destroy$))
            .subscribe(n => this.notifications = n);
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    markAllRead(): void {
        this.notificationService.markAllRead();
    }

    formatTime(date: Date): string {
        return new Date(date).toLocaleTimeString('en-US', {
            hour: '2-digit', minute: '2-digit'
        });
    }

    getIcon(type: string): string {
        switch (type) {
            case 'TOKEN_CREATED':
                return 'pi pi-check-circle';
            case 'TOKEN_CANCELLED':
                return 'pi pi-times-circle';
            case 'TOKEN_SKIPPED':
                return 'pi pi-forward';
            default:
                return 'pi pi-info-circle';
        }
    }
}