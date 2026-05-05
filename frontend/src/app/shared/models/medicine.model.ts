export interface Medicine {
    deletedOn?: string;
    id: string;
    productId?: string; // Added for form compatibility
    name: string;
    salt: string;  // salt name
    batchNumber: string;
    quantity: number;
    purchasedPrice: number;  // cost price
    sellingPrice: number;   // selling price
    manufactureDate: string;
    expiryDate: string;
    supplierName: string;
    distributorName: string;
    distributorMobile: string;
    distributorCompany: string;
    status?: string; // Medicine status (Active, Low Stock, Expired, etc.)
    genericName?: string;
    type?: string;
    category?: string;
    subCategory?: string;
    stockUnit?: string;
}

export type MedicineStatus = 'Active' | 'Low Stock' | 'Expired';
