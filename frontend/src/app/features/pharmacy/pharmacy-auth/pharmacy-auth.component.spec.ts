import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PharmacyAuthComponent } from './pharmacy-auth.component';

describe('PharmacyAuthComponent', () => {
  let component: PharmacyAuthComponent;
  let fixture: ComponentFixture<PharmacyAuthComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PharmacyAuthComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(PharmacyAuthComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
