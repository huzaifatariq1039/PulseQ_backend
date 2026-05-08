import { Routes } from '@angular/router';
import { environment } from '../environments/environment';

import { patientRoutes } from './routes/patient.routes';
import { doctorRoutes } from './routes/doctor.routes';
import { pharmacyRoutes } from './routes/pharmacy.routes';
import { receptionRoutes } from './routes/reception.routes';
import { adminRoutes } from './routes/admin.routes';
import { demoRoutes } from './routes/demo.routes';
import { mainRoutes } from './routes/main.routes';

const portalRouteMap: Record<string, Routes> = {
    patient: patientRoutes,
    doctor: doctorRoutes,
    pharmacy: pharmacyRoutes,
    reception: receptionRoutes,
    admin: adminRoutes,
    demo: demoRoutes,
    main: mainRoutes,
};

export const routes: Routes = portalRouteMap[environment.portal] || mainRoutes;