import { Component, EventEmitter, HostListener, Input, OnInit, Output } from '@angular/core';
import { RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';

@Component({
    selector: 'app-doctor-sidebar',
    standalone: true,
    imports: [RouterModule, CommonModule],
    templateUrl: './doctor-sidebar.component.html',
    styleUrls: ['./doctor-sidebar.component.css']
})
export class DoctorSidebarComponent implements OnInit {
    /** Controls whether the sidebar is visible (used for mobile). */
    @Input() open = true;

    /** Emitted when a navigation item is clicked or the sidebar should close. */
    @Output() close = new EventEmitter<void>();

    /** Emitted when the sign‑out button is clicked. */
    @Output() signOut = new EventEmitter<void>();

    isMobile = false;


    ngOnInit(): void {
        this.checkMobile();
    }

    @HostListener('window:resize')
    checkMobile(): void {
        if (typeof window !== 'undefined') {
            this.isMobile = window.innerWidth <= 900;
        } else {
            this.isMobile = false;
        }
    }

    handleLinkClick(): void {
        this.close.emit();
    }

    handleSignOut(): void {
        this.signOut.emit();
    }
}