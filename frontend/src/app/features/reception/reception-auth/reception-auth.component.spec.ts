import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ReceptionAuthComponent } from './reception-auth.component';

describe('ReceptionAuthComponent', () => {
  let component: ReceptionAuthComponent;
  let fixture: ComponentFixture<ReceptionAuthComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReceptionAuthComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(ReceptionAuthComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
