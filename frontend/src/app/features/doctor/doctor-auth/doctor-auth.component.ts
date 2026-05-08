import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextModule } from 'primeng/inputtext';
import { InputGroupModule } from 'primeng/inputgroup';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-doctor-auth',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ButtonModule,
    CardModule,
    InputTextModule,
    InputGroupModule,
    ToastModule
  ],
  providers: [MessageService],
  templateUrl: './doctor-auth.component.html',
  styleUrl: './doctor-auth.component.css'
})
export class DoctorAuthComponent implements OnInit {
  loginForm!: FormGroup;
  
  // ✅ Signals replace isLoading state variable
  readonly showPassword = signal(false);
  readonly isLoading = signal(false);

  private authService = inject(AuthService);
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private messageService = inject(MessageService);

  ngOnInit(): void {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]]
    });
  }

  get f() {
    return this.loginForm.controls;
  }

  submitForm(): void {
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    const { email, password } = this.loginForm.value;

    // ✅ HttpClient Observable automatically completes after response
    // No manual cleanup needed—subscribe safely without takeUntilDestroyed()
    this.authService.login(email, password, 'email', 'doctor')
      .subscribe({
        next: (success) => {
          this.isLoading.set(false);
          if (success) {
            this.messageService.add({
              severity: 'success',
              summary: 'Login Successful',
              detail: `Welcome, Doctor!`,
              life: 2000
            });
            setTimeout(() => {
              this.router.navigate(['../dashboard'], { relativeTo: this.route });
            }, 500);
          } else {
            this.messageService.add({
              severity: 'error',
              summary: 'Login Failed',
              detail: 'Invalid email or password.',
              life: 4000
            });
          }
        },
        error: (err) => {
          this.isLoading.set(false);
          this.messageService.add({
            severity: 'error',
            summary: 'Login Failed',
            detail: err?.error?.detail || 'Something went wrong. Please try again.',
            life: 4000
          });
        }
      });
  }

  goBack(): void {
    this.router.navigate(['../auth'], { relativeTo: this.route });
  }
}
