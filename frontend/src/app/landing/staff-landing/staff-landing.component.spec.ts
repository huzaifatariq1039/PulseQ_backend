import { StaffLandingComponent } from './staff-landing.component';
import { ComponentFixture, TestBed } from '@angular/core/testing';

describe('StaffLandingComponent', () => {
  let component: StaffLandingComponent;
  let fixture: ComponentFixture<StaffLandingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StaffLandingComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(StaffLandingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});