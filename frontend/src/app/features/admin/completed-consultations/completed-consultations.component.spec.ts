import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CompletedConsultationsComponent } from './completed-consultations.component';

describe('CompletedConsultationsComponent', () => {
    let component: CompletedConsultationsComponent;
    let fixture: ComponentFixture<CompletedConsultationsComponent>;

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [CompletedConsultationsComponent]
        }).compileComponents();

        fixture = TestBed.createComponent(CompletedConsultationsComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
