import { Routes } from '@angular/router';

export const demoRoutes: Routes = [
    {
        path: '',
        loadComponent: () =>
            import('../features/demo-booking/demo-booking.component')
                .then(m => m.DemoBookingComponent)
    }
];
