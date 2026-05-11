import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { PatientHeaderComponent } from '../shared/components/patient-header/patient-header.component';
//primeng
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { CardModule } from 'primeng/card';
import { MessageService } from 'primeng/api';
//services
import { AuthService } from '../../../core/services/auth.service';
import { UserProfileService, UserProfile } from '../../../core/services/user-profile.service';

@Component({
    selector: 'app-patient-profile',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        ButtonModule,
        InputTextModule,
        DialogModule,
        ToastModule,
        CardModule,
        PatientHeaderComponent
    ],
    providers: [MessageService],
    templateUrl: './patient-profile.component.html',
    styleUrls: ['./patient-profile.component.css']
})
export class PatientProfileComponent implements OnInit {
    userProfile: UserProfile | null = null;

    editNameForm!: FormGroup;
    editEmailForm!: FormGroup;
    changePasswordForm!: FormGroup;

    showEditNameDialog = false;
    showEditEmailDialog = false;
    showChangePasswordDialog = false;

    savingName = false;
    savingEmail = false;

    constructor(
        private fb: FormBuilder,
        private router: Router,
        private messageService: MessageService,
        private authService: AuthService,
        private userProfileService: UserProfileService
    ) { }

    ngOnInit(): void {
        this.initializeForms();
        this.loadUserProfile();
        this.userProfileService.profile$.subscribe(profile => {
            this.userProfile = profile;
        });
    }

    private initializeForms(): void {
        this.editNameForm = this.fb.group({
            firstName: ['', [Validators.required, Validators.minLength(2)]],
            lastName: ['', [Validators.required, Validators.minLength(2)]]
        });

        this.editEmailForm = this.fb.group({
            currentEmail: [{ value: '', disabled: true }, Validators.required],
            newEmail: ['', [Validators.required, Validators.email]],
            confirmEmail: ['', [Validators.required, Validators.email]]
        }, { validators: this.emailMatchValidator });

        this.changePasswordForm = this.fb.group({
            currentPassword: ['', [Validators.required, Validators.minLength(6)]],
            newPassword: ['', [Validators.required, Validators.minLength(6), Validators.pattern(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/)]],
            confirmPassword: ['', [Validators.required, Validators.minLength(6)]]
        }, { validators: this.passwordMatchValidator });
    }

    private loadUserProfile(): void {
        this.userProfile = this.userProfileService.getProfile();
        if (this.userProfile) {
            this.populateForms(this.userProfile);
        } else {
            this.userProfileService.fetchProfile().subscribe({
                next: () => {
                    this.userProfile = this.userProfileService.getProfile();
                    if (this.userProfile) {
                        this.populateForms(this.userProfile);
                    }
                },
                error: () => {
                    const authUser = this.authService.getCurrentUser();
                    if (authUser) {
                        const nameParts = (authUser.name || '').split(' ');
                        this.userProfile = {
                            fullName: authUser.name || '',
                            email: authUser.email || '',
                            profilePicture: null,
                            initials: nameParts.map((n: string) => n[0]).join('').toUpperCase() || '?',
                            phone: authUser.phone
                        };
                        this.userProfileService.saveProfile(this.userProfile);
                        this.populateForms(this.userProfile);
                    }
                }
            });
        }
    }

    private populateForms(profile: UserProfile): void {
        const names = profile.fullName.split(' ');
        this.editNameForm.patchValue({
            firstName: names[0],
            lastName: names[1] || ''
        });
        this.editEmailForm.patchValue({
            currentEmail: profile.email
        });
    }

    emailMatchValidator(group: FormGroup): Record<string, unknown> | null {
        const newEmail = group.get('newEmail')?.value;
        const confirmEmail = group.get('confirmEmail')?.value;
        if (newEmail && confirmEmail && newEmail !== confirmEmail) {
            group.get('confirmEmail')?.setErrors({ emailMismatch: true });
            return { emailMismatch: true };
        } else {
            const errors = group.get('confirmEmail')?.errors;
            if (errors) {
                delete errors['emailMismatch'];
                if (Object.keys(errors).length === 0) {
                    group.get('confirmEmail')?.setErrors(null);
                }
            }
        }
        return null;
    }

    passwordMatchValidator(group: FormGroup): Record<string, unknown> | null {
        const newPassword = group.get('newPassword')?.value;
        const confirmPassword = group.get('confirmPassword')?.value;
        if (newPassword && confirmPassword && newPassword !== confirmPassword) {
            group.get('confirmPassword')?.setErrors({ passwordMismatch: true });
            return { passwordMismatch: true };
        } else {
            const errors = group.get('confirmPassword')?.errors;
            if (errors) {
                delete errors['passwordMismatch'];
                if (Object.keys(errors).length === 0) {
                    group.get('confirmPassword')?.setErrors(null);
                }
            }
        }
        return null;
    }

    openEditNameDialog(): void {
        const names = this.userProfile ? this.userProfile.fullName.split(' ') : ['', ''];
        this.editNameForm.patchValue({
            firstName: names[0],
            lastName: names[1] || ''
        });
        this.showEditNameDialog = true;
    }

    saveEditName(): void {
        if (this.editNameForm.invalid) return;
        const { firstName, lastName } = this.editNameForm.value;
        const fullName = `${firstName} ${lastName}`;
        this.savingName = true;

        this.userProfileService.updateProfileApi({ name: fullName }).subscribe({
            next: () => {
                this.userProfileService.updateFullName(fullName);
                this.savingName = false;
                this.showEditNameDialog = false;
                this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Name updated successfully', life: 3000 });
            },
            error: (err) => {
                this.savingName = false;
                let errorMsg = 'Failed to update name. Please try again.';
                if (err?.error?.detail) {
                    errorMsg = typeof err.error.detail === 'string' ? err.error.detail : 'Update failed';
                }
                this.messageService.add({ severity: 'error', summary: 'Error', detail: errorMsg, life: 4000 });
            }
        });
    }

    cancelEditName(): void {
        this.showEditNameDialog = false;
        this.editNameForm.reset();
    }

    openEditEmailDialog(): void {
        this.editEmailForm.patchValue({
            currentEmail: this.userProfile ? this.userProfile.email : '',
            newEmail: '',
            confirmEmail: ''
        });
        this.showEditEmailDialog = true;
    }

    saveEditEmail(): void {
        if (this.editEmailForm.invalid) return;
        const { newEmail } = this.editEmailForm.value;
        this.savingEmail = true;

        this.userProfileService.updateProfileApi({ email: newEmail }).subscribe({
            next: () => {
                this.userProfileService.updateEmail(newEmail);
                this.savingEmail = false;
                this.showEditEmailDialog = false;
                this.editEmailForm.reset();
                this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Email updated successfully', life: 3000 });
            },
            error: (err) => {
                this.savingEmail = false;
                let errorMsg = 'Failed to update email. Please try again.';
                if (err?.error?.detail) {
                    errorMsg = typeof err.error.detail === 'string' ? err.error.detail : 'Update failed';
                }
                this.messageService.add({ severity: 'error', summary: 'Error', detail: errorMsg, life: 4000 });
            }
        });
    }

    cancelEditEmail(): void {
        this.showEditEmailDialog = false;
        this.editEmailForm.reset();
    }

    openChangePasswordDialog(): void {
        this.changePasswordForm.reset();
        this.showChangePasswordDialog = true;
    }

    saveChangePassword(): void {
        if (this.changePasswordForm.invalid) return;
        const { currentPassword, newPassword } = this.changePasswordForm.value;
        this.userProfileService.changePassword(currentPassword, newPassword).subscribe({
            next: () => {
                this.showChangePasswordDialog = false;
                this.changePasswordForm.reset();
                this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Password updated successfully', life: 3000 });
            },
            error: (err) => {
                let errorMsg = 'Failed to update password. Please check your current password.';
                if (err?.error?.detail) {
                    if (Array.isArray(err.error.detail)) {
                        errorMsg = err.error.detail.map((e: any) => e.msg).join(', ');
                    } else if (typeof err.error.detail === 'string') {
                        errorMsg = err.error.detail;
                    }
                }
                this.messageService.add({ severity: 'error', summary: 'Error', detail: errorMsg, life: 4000 });
            }
        });
    }

    cancelChangePassword(): void {
        this.showChangePasswordDialog = false;
        this.changePasswordForm.reset();
    }

    logout(): void {
        this.authService.logout();
        this.router.navigate(['/']);
    }

    get editNameFirstName() { return this.editNameForm.get('firstName'); }
    get editNameLastName() { return this.editNameForm.get('lastName'); }
    get editEmailNewEmail() { return this.editEmailForm.get('newEmail'); }
    get editEmailConfirmEmail() { return this.editEmailForm.get('confirmEmail'); }
    get changePasswordCurrentPassword() { return this.changePasswordForm.get('currentPassword'); }
    get changePasswordNewPassword() { return this.changePasswordForm.get('newPassword'); }
    get changePasswordConfirmPassword() { return this.changePasswordForm.get('confirmPassword'); }
}