import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class DiagnosticService {
  private http = inject(HttpClient);

  /**
   * Test basic backend connectivity
   */
  testConnectivity(): Observable<any> {
    console.log('[Diagnostic] Testing backend connectivity...');
    return this.http.get(`${environment.apiBaseUrl.split('/api/v1')[0]}/ping`);
  }

  /**
   * Test if admin user can access portal endpoints
   */
  testAdminAccess(): Observable<any> {
    console.log('[Diagnostic] Testing admin access to portal endpoints...');
    return this.http.get(`${environment.apiBaseUrl}/portal/completed-consultations?page=1&page_size=1`);
  }

  /**
   * Test if admin user can access pharmacy endpoints
   */
  testPharmacyAccess(): Observable<any> {
    console.log('[Diagnostic] Testing admin access to pharmacy endpoints...');
    return this.http.get(`${environment.apiBaseUrl}/staff/pharmacy/dashboard/stats`);
  }

  /**
   * Run all diagnostics
   */
  runAllDiagnostics(): Observable<any> {
    return new Observable(observer => {
      const results: any = {
        timestamp: new Date().toISOString(),
        tests: {}
      };

      // Test 1: Connectivity
      this.testConnectivity().subscribe({
        next: (res) => {
          results.tests.connectivity = { status: 'PASS', data: res };
          console.log('[Diagnostic] ✓ Connectivity test passed');

          // Test 2: Admin Access
          this.testAdminAccess().subscribe({
            next: (res) => {
              results.tests.adminAccess = { status: 'PASS', data: res };
              console.log('[Diagnostic] ✓ Admin access test passed');

              // Test 3: Pharmacy Access
              this.testPharmacyAccess().subscribe({
                next: (res) => {
                  results.tests.pharmacyAccess = { status: 'PASS', data: res };
                  console.log('[Diagnostic] ✓ Pharmacy access test passed');
                  
                  console.log('[Diagnostic] All diagnostics:', results);
                  observer.next(results);
                  observer.complete();
                },
                error: (err) => {
                  results.tests.pharmacyAccess = { status: 'FAIL', error: err.message, status_code: err.status };
                  console.error('[Diagnostic] ✗ Pharmacy access test failed:', err);
                  
                  console.log('[Diagnostic] All diagnostics:', results);
                  observer.next(results);
                  observer.complete();
                }
              });
            },
            error: (err) => {
              results.tests.adminAccess = { status: 'FAIL', error: err.message, status_code: err.status };
              console.error('[Diagnostic] ✗ Admin access test failed:', err);

              // Still try pharmacy test
              this.testPharmacyAccess().subscribe({
                next: (res) => {
                  results.tests.pharmacyAccess = { status: 'PASS', data: res };
                  console.log('[Diagnostic] ✓ Pharmacy access test passed');
                  
                  console.log('[Diagnostic] All diagnostics:', results);
                  observer.next(results);
                  observer.complete();
                },
                error: (err) => {
                  results.tests.pharmacyAccess = { status: 'FAIL', error: err.message, status_code: err.status };
                  console.error('[Diagnostic] ✗ Pharmacy access test failed:', err);
                  
                  console.log('[Diagnostic] All diagnostics:', results);
                  observer.next(results);
                  observer.complete();
                }
              });
            }
          });
        },
        error: (err) => {
          results.tests.connectivity = { status: 'FAIL', error: err.message };
          console.error('[Diagnostic] ✗ Connectivity test failed:', err);
          observer.next(results);
          observer.complete();
        }
      });
    });
  }
}
