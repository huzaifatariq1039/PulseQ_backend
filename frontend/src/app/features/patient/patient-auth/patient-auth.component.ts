import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-patient-auth',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ButtonModule,
    CardModule,
    InputTextModule,
    PasswordModule,
    ToastModule
  ],
  providers: [MessageService],
  templateUrl: './patient-auth.component.html',
  styleUrls: ['./patient-auth.component.css']
})
export class PatientAuthComponent implements OnInit {
  authForm!: FormGroup;
  isLoginMode = true;
  isForgotMode = false;

  // Forgot password uses phone as the identifier
  forgotPasswordStep: 'phone' | 'otp' | 'reset' = 'phone';
  forgotPasswordPhone = '';
  forgotPasswordOtp = '';

  showPassword = false;
  isLoading = false;
  resendOtpCountdown = 0;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private route: ActivatedRoute,
    private authService: AuthService,
    private messageService: MessageService
  ) { }

  ngOnInit(): void {
    this.buildForm();
  }

  private buildForm(): void {
    // ── Forgot Password Steps ──────────────────────────────────────────────
    if (this.isForgotMode) {
      if (this.forgotPasswordStep === 'phone') {
        this.authForm = this.fb.group({
          phone: ['', [Validators.required, Validators.pattern(/^[0-9]{7,15}$/)]]
        });

      } else if (this.forgotPasswordStep === 'otp') {
        this.authForm = this.fb.group({
          otp: ['', [Validators.required, Validators.pattern(/^\d{4,8}$/)]]
        });

      } else if (this.forgotPasswordStep === 'reset') {
        this.authForm = this.fb.group({
          newPassword: [
            '',
            [
              Validators.required,
              Validators.minLength(6),
              Validators.pattern(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/)
            ]
          ],
          confirmPassword: ['', Validators.required]
        }, {
          validators: this.passwordsMatchValidator()
        });
      }
      return;
    }

    // ── Login / Signup Form ───────────────────────────────────────────────
    const passwordValidators = this.isLoginMode
      ? [Validators.required]
      : [
        Validators.required,
        Validators.minLength(6),
        Validators.pattern(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/)
      ];

    this.authForm = this.fb.group({
      ...(this.isLoginMode ? {} : { name: ['', Validators.required] }),
      email: ['', [Validators.required, Validators.email]],
      password: ['', passwordValidators],
      ...(this.isLoginMode ? {} : {
        phone: ['', [Validators.required, Validators.pattern(/^[0-9]{7,15}$/)]]
      }),
      ...(this.isLoginMode ? {} : { confirmPassword: ['', Validators.required] })
    }, {
      validators: this.isLoginMode ? null : this.passwordsMatchValidator()
    });
  }

  private passwordsMatchValidator() {
    return (group: FormGroup) => {
      const pw = group.get('password')?.value;
      const cpw = group.get('confirmPassword')?.value;
      return pw && cpw && pw !== cpw ? { mismatch: true } : null;
    };
  }

  get f() {
    return this.authForm.controls;
  }

  // ── Mode Toggles ───────────────────────────────────────────────────────────

  toggleMode(): void {
    const email = this.authForm?.get('email')?.value ?? '';
    const name = this.authForm?.get('name')?.value ?? '';
    const phone = this.authForm?.get('phone')?.value ?? '';
    const password = this.authForm?.get('password')?.value ?? '';
    const confirmPassword = this.authForm?.get('confirmPassword')?.value ?? '';

    this.isLoginMode = !this.isLoginMode;
    this.isForgotMode = false;
    this.forgotPasswordStep = 'phone';
    this.buildForm();
    this.authForm.patchValue({ name, email, phone, password, confirmPassword });
  }

  showForgotPassword(): void {
    this.isForgotMode = true;
    this.forgotPasswordStep = 'phone';
    this.forgotPasswordPhone = '';
    this.forgotPasswordOtp = '';
    this.resendOtpCountdown = 0;
    this.buildForm();
  }

  backToLogin(): void {
    this.isForgotMode = false;
    this.forgotPasswordStep = 'phone';
    this.forgotPasswordPhone = '';
    this.forgotPasswordOtp = '';
    this.resendOtpCountdown = 0;
    this.isLoginMode = true;
    this.buildForm();
  }

  // ── Forgot Password Flow ───────────────────────────────────────────────────

  private submitForgotPasswordPhone(): void {
    if (this.authForm.invalid) {
      this.authForm.markAllAsTouched();
      return;
    }
    this.isLoading = true;
    const { phone } = this.authForm.value;
    this.forgotPasswordPhone = phone;

    this.authService.forgotPassword(phone).subscribe({
      next: () => {
        this.isLoading = false;
        this.forgotPasswordStep = 'otp';
        this.resendOtpCountdown = 60;
        this.startResendOtpCountdown();
        this.buildForm();
        this.messageService.add({
          severity: 'success',
          summary: 'OTP Sent',
          detail: `A verification OTP has been sent to ${this.maskPhoneNumber(phone)}.`,
          life: 4000
        });
      },
      error: (err) => {
        this.isLoading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Failed',
          detail: err?.error?.message || err?.error?.detail || 'Could not send OTP. Please check your phone number.',
          life: 4000
        });
      }
    });
  }

  private submitOtp(): void {
    if (this.authForm.invalid) {
      this.authForm.markAllAsTouched();
      return;
    }
    this.isLoading = true;
    const { otp } = this.authForm.value;
    this.forgotPasswordOtp = otp;

    this.authService.verifyOtp(this.forgotPasswordPhone, otp).subscribe({
      next: () => {
        this.isLoading = false;
        this.forgotPasswordStep = 'reset';
        this.buildForm();
        this.messageService.add({
          severity: 'success',
          summary: 'OTP Verified',
          detail: 'Please enter your new password.',
          life: 3000
        });
      },
      error: (err) => {
        this.isLoading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Invalid OTP',
          detail: err?.error?.message || err?.error?.detail || 'The OTP you entered is incorrect or has expired.',
          life: 4000
        });
      }
    });
  }

  private submitResetPassword(): void {
    if (this.authForm.invalid) {
      this.authForm.markAllAsTouched();
      return;
    }
    this.isLoading = true;
    const { newPassword } = this.authForm.value;

    this.authService.resetPasswordWithOtp(
      this.forgotPasswordPhone,
      this.forgotPasswordOtp,
      newPassword
    ).subscribe({
      next: () => {
        this.isLoading = false;
        this.messageService.add({
          severity: 'success',
          summary: 'Password Reset Successful',
          detail: 'Your password has been reset. Please login with your new password.',
          life: 3000
        });
        setTimeout(() => {
          this.backToLogin();
        }, 2000);
      },
      error: (err) => {
        this.isLoading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Failed',
          detail: err?.error?.message || err?.error?.detail || 'Could not reset password. Please try again.',
          life: 4000
        });
      }
    });
  }

  resendOtp(): void {
    this.isLoading = true;
    this.authService.resendOtp(this.forgotPasswordPhone).subscribe({
      next: () => {
        this.isLoading = false;
        this.resendOtpCountdown = 60;
        this.startResendOtpCountdown();
        this.messageService.add({
          severity: 'success',
          summary: 'OTP Resent',
          detail: `A new OTP has been sent to ${this.maskPhoneNumber(this.forgotPasswordPhone)}.`,
          life: 3000
        });
      },
      error: (err) => {
        this.isLoading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Failed',
          detail: err?.error?.message || err?.error?.detail || 'Could not resend OTP. Please try again.',
          life: 4000
        });
      }
    });
  }

  submitForgotPassword(): void {
    if (this.forgotPasswordStep === 'phone') {
      this.submitForgotPasswordPhone();
    } else if (this.forgotPasswordStep === 'otp') {
      this.submitOtp();
    } else if (this.forgotPasswordStep === 'reset') {
      this.submitResetPassword();
    }
  }

  // ── Main Submit Router ─────────────────────────────────────────────────────

  submit(): void {
    if (this.isForgotMode) {
      this.submitForgotPassword();
      return;
    }

    if (this.authForm.invalid) {
      this.authForm.markAllAsTouched();
      return;
    }

    this.isLoading = true;

    if (this.isLoginMode) {
      // ── Login ──────────────────────────────────────────────────────────
      const { email, password } = this.authForm.value;
      this.authService.login(email, password, 'email', 'patient').subscribe({
        next: (success) => {
          this.isLoading = false;
          if (success) {
            this.messageService.add({
              severity: 'success',
              summary: 'Login Successful',
              detail: 'Welcome back!',
              life: 2000
            });
            setTimeout(() => {
              this.router.navigate(['../dashboard'], { relativeTo: this.route });
            }, 500);
          } else {
            this.messageService.add({
              severity: 'error',
              summary: 'Login Failed',
              detail: 'Invalid email or password. Please try again.',
              life: 4000
            });
          }
        },
        error: (err) => {
          this.isLoading = false;
          this.messageService.add({
            severity: 'error',
            summary: 'Login Failed',
            detail: err?.error?.message || err?.error?.detail || 'Something went wrong. Please try again.',
            life: 4000
          });
        }
      });

    } else {
      // ── Registration (direct, no OTP step) ────────────────────────────
      const { name, email, phone, password } = this.authForm.value;
      this.authService.register({ name, email, phone, password, auth_method: 'email' }).subscribe({
        next: () => {
          this.isLoading = false;
          this.messageService.add({
            severity: 'success',
            summary: 'Registration Successful',
            detail: 'Account created successfully. Please login.',
            life: 3000
          });
          this.isLoginMode = true;
          this.buildForm();
          this.authForm.patchValue({ email });
        },
        error: (err) => {
          this.isLoading = false;
          this.messageService.add({
            severity: 'error',
            summary: 'Registration Failed',
            detail: err?.error?.message || err?.error?.detail || 'Could not create account. Please try again.',
            life: 4000
          });
        }
      });
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  maskPhoneNumber(phone: string): string {
    if (!phone || phone.length < 4) return phone;
    return '*'.repeat(phone.length - 4) + phone.slice(-4);
  }

  private startResendOtpCountdown(): void {
    const interval = setInterval(() => {
      this.resendOtpCountdown--;
      if (this.resendOtpCountdown <= 0) {
        clearInterval(interval);
      }
    }, 1000);
  }

  goBack(): void {
    this.router.navigate(['/']);
  }
}