export interface InvoiceItem {
    id?: string;
    invoice_id?: string;
    medicine_id?: string | null;
    product_id: number | null;
    product_name: string;
    product_code?: string | null;
    quantity: number;
    unit_price: number;
    discount: number;
    total?: number;
    created_at?: string;
}

export interface Invoice {
    id?: string;
    invoice_number?: string;
    customer_id?: string | null;
    customer_name: string;
    status: 'pending' | 'completed' | 'partial' | 'cancel';
    payment_method: 'cash' | 'card' | 'online' | 'other';
    subtotal?: number;
    discount: number;
    discount_percent?: number;
    tax: number;
    total?: number;
    amount_paid?: number;
    balance_due?: number;
    notes?: string;
    hospital_id?: string;
    created_by?: string;
    is_deleted?: boolean;
    deleted_at?: string | null;
    created_at?: string;
    updated_at?: string | null;
    items?: InvoiceItem[];
    item_count?: number;
}

export interface InvoiceCounts {
    all: number;
    completed: number;
    pending: number;
    partial: number;
    cancelled: number;
}

export interface InvoiceListData {
    invoices: Invoice[];
    counts: InvoiceCounts;
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
}

export interface InvoiceListParams {
    status?: string;
    search?: string;
    date_from?: string;
    date_to?: string;
}

export interface ApiResponse<T> {
    success: boolean;
    message: string;
    data: T;
}