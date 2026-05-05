// import { TestBed } from '@angular/core/testing';

// import { ConsultationService } from './consultation.service';
// import { QueueService } from './queue.service';

// describe('ConsultationServiceTsService', () => {
//   let service: ConsultationService;
//   let queueSpy: jasmine.SpyObj<any>;

//   beforeEach(() => {
//     const spy = jasmine.createSpyObj('QueueService', [
//       'updateTokenStatus',
//       'removeToken',
//       'getTokenById'
//     ]);
//     TestBed.configureTestingModule({
//       providers: [
//         { provide: QueueService, useValue: spy }
//       ]
//     });
//     queueSpy = spy;
//     service = TestBed.inject(ConsultationService);
//   });

//   it('should be created', () => {
//     expect(service).toBeTruthy();
//   });

//   it('finishConsultation updates status but does not remove token', () => {
//     const fakeToken = { id: '123', tokenNumber: 'A-001' };
//     queueSpy.getTokenById.and.returnValue(fakeToken);

//     service.finishConsultation('123', 'notes');

//     expect(queueSpy.updateTokenStatus).toHaveBeenCalledWith('123', 'DONE');
//     expect(queueSpy.removeToken).not.toHaveBeenCalled();
//   });
// });
