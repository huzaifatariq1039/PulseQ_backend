// import { ComponentFixture, TestBed } from '@angular/core/testing';

// import { PatientProfileComponent } from './patient-profile.component';

// describe('PatientProfileComponent', () => {
//     let component: PatientProfileComponent;
//     let fixture: ComponentFixture<PatientProfileComponent>;

//     beforeEach(async () => {
//         await TestBed.configureTestingModule({
//             imports: [PatientProfileComponent]
//         })
//             .compileComponents();

//         fixture = TestBed.createComponent(PatientProfileComponent);
//         component = fixture.componentInstance;
//         fixture.detectChanges();
//     });

//     it('should create', () => {
//         expect(component).toBeTruthy();
//     });

//     it('should initialize forms on init', () => {
//         expect(component.editNameForm).toBeDefined();
//         expect(component.editEmailForm).toBeDefined();
//         expect(component.changePasswordForm).toBeDefined();
//     });

//     it('should validate email match in edit email form', () => {
//         component.editEmailForm.patchValue({
//             newEmail: 'test@example.com',
//             confirmEmail: 'different@example.com'
//         });
//         expect(component.editEmailForm.hasError('emailMismatch')).toBeTruthy();
//     });

//     it('should validate password match in change password form', () => {
//         component.changePasswordForm.patchValue({
//             newPassword: 'password123',
//             confirmPassword: 'different123'
//         });
//         expect(component.changePasswordForm.hasError('passwordMismatch')).toBeTruthy();
//     });

//     it('should open and close edit name dialog', () => {
//         expect(component.showEditNameDialog).toBeFalsy();
//         component.openEditNameDialog();
//         expect(component.showEditNameDialog).toBeTruthy();
//         component.cancelEditName();
//         expect(component.showEditNameDialog).toBeFalsy();
//     });

//     it('should update full name on save', () => {
//         const initialName = component.userProfile!.fullName;
//         component.editNameForm.patchValue({
//             firstName: 'Jane',
//             lastName: 'Smith'
//         });
//         component.openEditNameDialog();
//         component.saveEditName();
//         expect(component.userProfile!.fullName).toBe('Jane Smith');
//         expect(component.userProfile!.fullName).not.toBe(initialName);
//     });
// });
