import { Routes } from '@angular/router';
import { patientRoutes } from './patient.routes';
import { doctorRoutes } from './doctor.routes';
import { receptionRoutes } from './reception.routes';
import { adminRoutes } from './admin.routes';
import { pharmacyRoutes } from './pharmacy.routes';

export const mainRoutes: Routes = [
    {
        path: '',
        loadComponent: () =>
            import('../landing/landing-page/landing-page.component')
                .then(m => m.LandingPageComponent)
    },
    {
        path: 'staff',
        children: [
            {
                path: '',
                loadComponent: () =>
                    import('../landing/staff-landing/staff-landing.component')
                        .then(m => m.StaffLandingComponent)
            },
            {
                path: 'doctor',
                children: doctorRoutes
            },
            {
                path: 'reception',
                children: receptionRoutes
            },
            {
                path: 'admin',
                children: adminRoutes
            },
            {
                path: 'pharmacy',
                children: pharmacyRoutes
            }
        ]
    },
    {
        path: 'patient',
        children: patientRoutes
    }
];
