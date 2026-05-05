import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';

export const adminRoutes: Routes = [
    { path: '', redirectTo: 'auth', pathMatch: 'full' },
    {
        path: 'auth',
        loadComponent: () =>
            import('../features/admin/admin-auth/admin-auth.component')
                .then(m => m.AdminAuthComponent)
    },
    {
        path: 'completed-consultations',
        loadComponent: () =>
            import('../features/admin/completed-consultations/completed-consultations.component')
                .then(m => m.CompletedConsultationsComponent),
        canActivate: [authGuard]
    },
    {
        path: 'manage-doctors',
        loadComponent: () =>
            import('../features/admin/admin-manage-doctors/admin-manage-doctors.component')
                .then(m => m.AdminManageDoctorsComponent),
        canActivate: [authGuard]
    },
    {
        path: 'manage-departments',
        loadComponent: () =>
            import('../features/admin/admin-manage-departments/admin-manage-departments.component')
                .then(m => m.AdminManageDepartmentsComponent),
        canActivate: [authGuard]
    },
    {
        path: 'pharmacy-sales-revenue',
        loadComponent: () =>
            import('../features/admin/pharmacy-sales-revenue/admin-pharmacy-sales-revenue.component')
                .then(m => m.AdminPharmacySalesRevenueComponent),
        canActivate: [authGuard]
    },
    {
        path: 'dashboard',
        loadComponent: () =>
            import('../features/admin/admin-dashboard/admin-dashboard.component')
                .then(m => m.AdminDashboardComponent),
        canActivate: [authGuard]
    },
    // Legacy route redirects for backward compatibility
    { path: 'overview', redirectTo: 'dashboard' },
    { path: 'doctors', redirectTo: 'manage-doctors' },
    { path: 'departments', redirectTo: 'manage-departments' }
];
