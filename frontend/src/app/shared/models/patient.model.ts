interface Patient {
    token: string;
    name: string;
    age?: number;        // ← make optional
    gender?: string;     // ← make optional
    reason: string;
    status?: 'pending' | 'completed' | 'skipped';
    department?: string;
    phone?: string;
    paymentStatus?: 'paid' | 'unpaid';
    mrn?: string;
    doctorId?: string;
    doctorName?: string;
}