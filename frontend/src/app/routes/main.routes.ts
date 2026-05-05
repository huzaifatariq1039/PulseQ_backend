import { Routes } from '@angular/router';

export const mainRoutes: Routes = [
    {
        path: '',
        loadComponent: () =>
            import('../landing/landing-page/landing-page.component')
                .then(m => m.LandingPageComponent)
    },
    {
        path: 'staff',
        loadComponent: () =>
            import('../landing/staff-landing/staff-landing.component')
                .then(m => m.StaffLandingComponent)
    }
];
