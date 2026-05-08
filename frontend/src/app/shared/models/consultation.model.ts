import { DoctorRating } from './doctor-rating.model';

export interface Consultation {
    id: string;
    patientId: string;
    patientName?: string;
    doctorId: string;
    doctorName?: string;
    tokenId: string;
    tokenNumber?: string;
    reason?: string;
    phone?: string;
    notes?: string;
    startTime: Date;
    endTime?: Date;
    rating?: DoctorRating;
    // additional metadata copied from token when consultation completes
    department?: string;
    patientAge?: number;
    patientGender?: string;
    patientCNIC?: string;
    patientMRN?: string;
    createdAt?: Date;
}
