import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';

export const patientRoutes: Routes = [
    { path: '', redirectTo: 'auth', pathMatch: 'full' },
    {
        path: 'auth',
        loadComponent: () =>
            import('../features/patient/patient-auth/patient-auth.component')
                .then(m => m.PatientAuthComponent)
    },
    {
        path: 'dashboard',
        loadComponent: () =>
            import('../features/patient/patient-dashboard/patient-dashboard.component')
                .then(m => m.PatientDashboardComponent),
        canActivate: [authGuard]
    },
    {
        path: 'new-token',
        loadComponent: () =>
            import('../features/patient/new-token/new-token.component')
                .then(m => m.NewTokenComponent),
        canActivate: [authGuard]
    },
    {
        path: 'my-token',
        loadComponent: () =>
            import('../features/patient/my-token/my-token.component')
                .then(m => m.MyTokenComponent),
        canActivate: [authGuard]
    },
    {
        path: 'live-status',
        loadComponent: () =>
            import('../features/patient/live-status/live-status.component')
                .then(m => m.LiveStatusComponent),
        canActivate: [authGuard]
    },
    {
        path: 'history',
        loadComponent: () =>
            import('../features/patient/patient-history/patient-history.component')
                .then(m => m.PatientHistoryComponent),
        canActivate: [authGuard]
    },
    {
        path: 'history/:id',
        loadComponent: () =>
            import('../features/patient/history-detail/history-detail.component')
                .then(m => m.HistoryDetailComponent),
        canActivate: [authGuard]
    },
    {
        path: 'notifications',
        loadComponent: () =>
            import('../features/patient/patient-notification/patient-notification.component')
                .then(m => m.PatientNotificationComponent),
        canActivate: [authGuard]
    },
    {
        path: 'profile',
        loadComponent: () =>
            import('../features/patient/patient-profile/patient-profile.component')
                .then(m => m.PatientProfileComponent),
        canActivate: [authGuard]
    }
];
