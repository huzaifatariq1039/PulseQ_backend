import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-pharmacy-auth',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, CardModule, ButtonModule, InputTextModule, ToastModule],
  providers: [MessageService],
  templateUrl: './pharmacy-auth.component.html',
  styleUrls: ['./pharmacy-auth.component.css']
})
export class PharmacyAuthComponent implements OnInit {
  loginForm: FormGroup;
  showPassword = false;
  isLoading = false;

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private messageService: MessageService,
    private authService: AuthService
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]]
    });
  }

  ngOnInit(): void { }

  get f() {
    return this.loginForm.controls;
  }

  submitForm() {
    if (this.loginForm.invalid) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Validation Error',
        detail: 'Please fill in all fields correctly',
        life: 3000
      });
      return;
    }

    this.isLoading = true;
    const { email, password } = this.loginForm.value;

    this.authService.pharmacyLogin(email, password).subscribe({
      next: (success) => {
        this.isLoading = false;

        const token = localStorage.getItem('pulseq_token');
        console.log('[PharmacyAuth] Login success flag:', success);
        console.log('[PharmacyAuth] Token in storage:', token);

        if (!success || !token) {
          this.messageService.add({
            severity: 'error',
            summary: 'Login Failed',
            detail: 'Authentication failed. Please check your credentials.',
            life: 4000
          });
          return;
        }

        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Logged in successfully',
          life: 2000
        });

        setTimeout(() => {
          this.router.navigate(['/staff/pharmacy/dashboard']).then(navigated => {
            console.log('[PharmacyAuth] Navigation to dashboard result:', navigated);
            if (!navigated) {
              console.error('[PharmacyAuth] Navigation failed — check route config and auth guard');
            }
          });
        }, 500);
      },
      error: (err) => {
        this.isLoading = false;
        console.error('[PharmacyAuth] Login error:', err);
        this.messageService.add({
          severity: 'error',
          summary: 'Login Failed',
          detail: err?.error?.detail || 'Something went wrong. Please try again.',
          life: 4000
        });
      }
    });
  }

  goBack() {
    this.router.navigate(['/auth']);
  }
}