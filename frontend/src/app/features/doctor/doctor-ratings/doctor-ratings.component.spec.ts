import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DoctorRatingsComponent } from './doctor-ratings.component';

describe('DoctorRatingsComponent', () => {
    let component: DoctorRatingsComponent;
    let fixture: ComponentFixture<DoctorRatingsComponent>;

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [DoctorRatingsComponent]
        })
            .compileComponents();

        fixture = TestBed.createComponent(DoctorRatingsComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
