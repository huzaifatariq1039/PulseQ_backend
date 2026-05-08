import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';

export const receptionRoutes: Routes = [
    { path: '', redirectTo: 'auth', pathMatch: 'full' },
    {
        path: 'auth',
        loadComponent: () =>
            import('../features/reception/reception-auth/reception-auth.component')
                .then(m => m.ReceptionAuthComponent)
    },
    {
        path: 'dashboard',
        loadComponent: () =>
            import('../features/reception/reception-dashboard/reception-dashboard.component')
                .then(m => m.ReceptionDashboardComponent),
        canActivate: [authGuard]
    },
    {
        path: 'queue',
        loadComponent: () =>
            import('../features/reception/reception-queue/reception-queue.component')
                .then(m => m.ReceptionQueueComponent),
        canActivate: [authGuard]
    },
    {
        path: 'manage-doctors',
        loadComponent: () =>
            import('../features/reception/reception-manage-doctors/reception-manage-doctors.component')
                .then(m => m.ReceptionManageDoctorsComponent),
        canActivate: [authGuard]
    }
];
