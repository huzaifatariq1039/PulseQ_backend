
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

import { environment } from '../../../../environments/environment';
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
      this.messageService.add({ severity: 'warn', summary: 'Error', detail: 'Please fill in all fields correctly', life: 3000 });
      return;
    }

    this.isLoading = true;
    const { email, password } = this.loginForm.value;

    this.authService.pharmacyLogin(email, password).subscribe({
      next: (success) => {
        this.isLoading = false;
        if (success) {
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: 'Logged in successfully',
            life: 2000
          });
          setTimeout(() => {
            const isLocalhost = window.location.hostname === 'localhost' ||
                                window.location.hostname === '127.0.0.1';

            if (isLocalhost) {
              this.router.navigate(['/staff/pharmacy/dashboard']);
            } else {
              this.router.navigate(['/dashboard']);
            }
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
        this.isLoading = false;
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
    this.router.navigate(['/']);
  }
}
