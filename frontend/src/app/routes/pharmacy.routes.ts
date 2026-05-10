import { Routes } from '@angular/router';
import { authGuard } from '../core/guards/auth.guard';

export const pharmacyRoutes: Routes = [
    { path: '', redirectTo: 'auth', pathMatch: 'full' },
    {
        path: 'auth',
        loadComponent: () =>
            import('../features/pharmacy/pharmacy-auth/pharmacy-auth.component')
                .then(m => m.PharmacyAuthComponent)
    },
    {
        path: 'dashboard',
        loadComponent: () =>
            import('../features/pharmacy/pharmacy-dashboard/pharmacy-dashboard.component')
                .then(m => m.PharmacyDashboardComponent),
        canActivate: [authGuard]
    },
    {
        path: 'inventory',
        loadComponent: () =>
            import('../features/pharmacy/inventory/inventory.component')
                .then(m => m.InventoryComponent),
        canActivate: [authGuard]
    },
    {
        path: 'sales',
        loadComponent: () =>
            import('../features/pharmacy/sales-revenue/sales-revenue.component')
                .then(m => m.SalesRevenueComponent),
        canActivate: [authGuard]
    },
    {
        path: 'add',
        loadComponent: () =>
            import('../features/pharmacy/medicine-form/medicine-form.component')
                .then(m => m.MedicineFormComponent),
        canActivate: [authGuard]
    },
    {
        path: 'trash',
        loadComponent: () =>
            import('../features/pharmacy/trash/pharmacy-trash.component')
                .then(m => m.PharmacyTrashComponent),
        canActivate: [authGuard]
    },
    {
        path: 'edit/:id',
        loadComponent: () =>
            import('../features/pharmacy/medicine-form/medicine-form.component')
                .then(m => m.MedicineFormComponent),
        canActivate: [authGuard]
    },
    {
        path: 'view/:id',
        loadComponent: () =>
            import('../features/pharmacy/medicine-form/medicine-form.component')
                .then(m => m.MedicineFormComponent),
        canActivate: [authGuard]
    }
];
