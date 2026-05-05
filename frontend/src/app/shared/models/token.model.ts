export interface Token {
    id: string;
    tokenNumber: string;
    patientId: string;
    doctorId: string;
    department: string;
    status: 'WAITING' | 'IN_PROGRESS' | 'DONE' | 'SKIPPED';
    createdAt: Date;
    startTime?: Date;
    endTime?: Date;
    // Optional UI fields kept for compatibility 
    hospital?: string;
    doctor?: string;
    reasonForVisit?: string;
    estimatedWait?: string;
    patientName?: string;
    patientPhone?: string;
    patientAge?: number;
    patientGender?: string;
    cnic?: string; // added for admin details
    specialNotes?: string;
    paymentStatus?: 'paid' | 'unpaid';
    mrn?: string; // Medical Record Number (backend-provided in future)
}
