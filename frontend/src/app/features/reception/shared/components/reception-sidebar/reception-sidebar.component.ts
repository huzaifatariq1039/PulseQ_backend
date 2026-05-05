import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

@Component({
    selector: 'app-reception-sidebar',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './reception-sidebar.component.html',
    styleUrls: ['./reception-sidebar.component.css']
})
export class ReceptionSidebarComponent {
    @Input() currentNav: 'dashboard' | 'queue' | 'manage-doctors' = 'dashboard';
    @Input() sidebarOpen = false;
    @Output() toggleSidebar = new EventEmitter<void>();
    @Output() navigate = new EventEmitter<'dashboard' | 'queue' | 'manage-doctors'>();
    @Output() signOut = new EventEmitter<void>();

    constructor(private router: Router) { }

    onNavigate(page: 'dashboard' | 'queue' | 'manage-doctors') {
        this.navigate.emit(page);
    }

    onToggleSidebar() {
        this.toggleSidebar.emit();
    }

    onSignOut() {
        this.signOut.emit();
        this.router.navigate(['/']);
    }
}
