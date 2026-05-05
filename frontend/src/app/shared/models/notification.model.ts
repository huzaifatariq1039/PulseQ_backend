export interface Notification {
    id: string;
    userId: string;
    message: string;
    type: 'TOKEN_CREATED' | 'WAIT_UPDATE' | 'CALL_PATIENT';
    createdAt: Date;
    read: boolean;
}
