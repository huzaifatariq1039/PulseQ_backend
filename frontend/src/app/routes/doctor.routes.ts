import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';

export const doctorRoutes: Routes = [
    { path: '', redirectTo: 'auth', pathMatch: 'full' },
    {
        path: 'auth',
        loadComponent: () =>
            import('../features/doctor/doctor-auth/doctor-auth.component')
                .then(m => m.DoctorAuthComponent)
    },
    {
        path: 'dashboard',
        loadComponent: () =>
            import('../features/doctor/doctor-dashboard/doctor-dashboard.component')
                .then(m => m.DoctorDashboardComponent),
        canActivate: [authGuard]
    },
    {
        path: 'ratings',
        loadComponent: () =>
            import('../features/doctor/doctor-ratings/doctor-ratings.component')
                .then(m => m.DoctorRatingsComponent),
        canActivate: [authGuard]
    },
    {
        path: 'history',
        loadComponent: () =>
            import('../features/doctor/patient-history/patient-history.component')
                .then(m => m.PatientHistoryComponent),
        canActivate: [authGuard]
    }
];
