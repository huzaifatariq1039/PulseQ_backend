import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { CalendarModule } from 'primeng/calendar';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { ToastModule } from 'primeng/toast';
import { DropdownModule } from 'primeng/dropdown';

import { MessageService } from 'primeng/api';
import { PharmacyService } from '../../../core/services/pharmacy.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';

@Component({
    selector: 'app-medicine-form',
    standalone: true,
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [
        CommonModule, RouterModule, FormsModule, ReactiveFormsModule,
        CardModule, ButtonModule, InputTextModule, InputNumberModule,
        CalendarModule, InputTextareaModule, ToastModule, DropdownModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService],
    templateUrl: './medicine-form.component.html',
    styleUrls: ['./medicine-form.component.css']
})
export class MedicineFormComponent implements OnInit {
    typeOptions = [
        { label: 'Medicine', value: 'Medicine' },
        { label: 'Equipment', value: 'Equipment' },
        { label: 'Surgical', value: 'Surgical' },
        { label: 'Syrup', value: 'Syrup' },
        { label: 'Injection', value: 'Injection' },
        { label: 'Tablet', value: 'Tablet' },
        { label: 'Capsule', value: 'Capsule' },
        { label: 'Cream', value: 'Cream' },
        { label: 'Drop', value: 'Drop' }
    ];

    stockUnitOptions = [
        { label: 'Box', value: 'Box' },
        { label: 'Strip', value: 'Strip' },
        { label: 'Bottle', value: 'Bottle' },
        { label: 'Piece', value: 'Piece' },
        { label: 'Vial', value: 'Vial' },
        { label: 'Sachet', value: 'Sachet' },
        { label: 'Tube', value: 'Tube' },
        { label: 'Packet', value: 'Packet' }
    ];
    isViewMode = false;
    medicineForm!: FormGroup;
    isEditing = false;
    medicineId: string | null = null;
    submitted = false;

    constructor(
        private formBuilder: FormBuilder,
        private pharmacyService: PharmacyService,
        private messageService: MessageService,
        private route: ActivatedRoute,
        private router: Router,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.initializeForm();
        this.checkIfEditing();
        // Auto-generate productId for new medicine
        if (!this.isEditing && !this.isViewMode) {
            this.pharmacyService.fetchAllMedicines().subscribe({
                next: (medicines: any[]) => {
                    let maxId = 0;
                    for (const med of medicines) {
                        const pid = parseInt(med.product_id ?? '0', 10);
                        if (!isNaN(pid) && pid > maxId) maxId = pid;
                    }
                    this.medicineForm.patchValue({ productId: (maxId + 1).toString() });
                    this.cdr.markForCheck();
                },
                error: (err) => {
                    console.error('Failed to fetch medicines for productId generation', err);
                    // Fallback to 1 if API fails
                    this.medicineForm.patchValue({ productId: '1' });
                }
            });
        }
    }

    initializeForm(): void {
        this.medicineForm = this.formBuilder.group({
            productId: ['', []], // optional, can be auto-generated or manual
            name: ['', [Validators.required]],
            genericName: ['', []],
            salt: ['', [Validators.required]],
            type: ['', []],
            category: ['', []],
            subCategory: ['', []],
            batchNumber: ['', [Validators.required]],
            stockUnit: ['', []],
            quantity: [0, [Validators.required, Validators.min(0)]],
            manufactureDate: [null, [Validators.required]],
            expiryDate: [null, [Validators.required]],
            purchasedPrice: [0, [Validators.required, Validators.min(0)]],
            sellingPrice: [0, [Validators.required, Validators.min(0)]],
            supplierName: ['', [Validators.required]],
            distributorName: ['', [Validators.required]],
            distributorMobile: ['', [Validators.required]],
            distributorCompany: ['', [Validators.required]]
        });
    }
    get totalPurchasePrice(): number {
        const form = this.medicineForm.value;
        return (form.purchasedPrice || 0) * (form.quantity || 0);
    }

    get totalSellingPrice(): number {
        const form = this.medicineForm.value;
        return (form.sellingPrice || 0) * (form.quantity || 0);
    }

    checkIfEditing(): void {
        this.route.params.subscribe(params => {
            if (params['id']) {
                this.medicineId = params['id'];
                if (this.router.url.includes('/view')) {
                    this.isViewMode = true;
                } else {
                    this.isEditing = true;
                }
                this.loadMedicineData();
                this.cdr.markForCheck();
            }
        });
    }

    loadMedicineData(): void {
        // Disable form if in view mode
        if (this.isViewMode) {
            this.medicineForm.disable();
        }
        if (this.medicineId) {
            // Fetch from API to get latest data
            this.pharmacyService.fetchAllMedicines().subscribe({
                next: (medicines: any[]) => {
                    const medicine = medicines.find(m => m.id === this.medicineId);
                    if (medicine) {
                        // Map API response to form fields
                        this.medicineForm.patchValue({
                            productId: medicine.product_id?.toString() || '',
                            name: medicine.name || '',
                            genericName: medicine.generic_name || '',
                            salt: medicine.generic_name || '', // salt is same as generic_name
                            type: medicine.type || '',
                            category: medicine.category || '',
                            subCategory: medicine.sub_category || '',
                            batchNumber: medicine.batch_no || '',
                            stockUnit: medicine.stock_unit || '',
                            quantity: medicine.quantity || 0,
                            manufactureDate: null, // API doesn't provide manufacture date
                            expiryDate: medicine.expiration_date ? new Date(medicine.expiration_date) : null,
                            purchasedPrice: medicine.purchase_price || 0,
                            sellingPrice: medicine.selling_price || 0,
                            supplierName: '', // API doesn't provide supplier name
                            distributorName: medicine.distributor || '',
                            distributorMobile: '', // API doesn't provide mobile
                            distributorCompany: medicine.distributor || ''
                        });
                        this.cdr.markForCheck();
                    } else {
                        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Medicine not found', life: 3000 });
                        this.router.navigate(['/staff/pharmacy/inventory']);
                    }
                },
                error: (err) => {
                    console.error('Failed to load medicine data', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load medicine data', life: 3000 });
                }
            });
        }
    }

    get f() { return this.medicineForm.controls; }

    onSubmit(): void {
        this.submitted = true;

        if (this.medicineForm.invalid) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Please fill in all required fields', life: 3000 });
            return;
        }

        const formData = this.medicineForm.value;
        const manufactureDate = formData.manufactureDate instanceof Date
            ? this.formatDateForAPI(formData.manufactureDate) : formData.manufactureDate;
        const expiryDate = formData.expiryDate instanceof Date
            ? this.formatDateForAPI(formData.expiryDate) : formData.expiryDate;
        const medicineData = { ...formData, manufactureDate, expiryDate };

        if (this.isEditing && this.medicineId) {
            // Map form data to API request format for update
            const apiRequest = {
                product_id: parseInt(medicineData.productId || '0', 10),
                batch_no: medicineData.batchNumber,
                name: medicineData.name,
                generic_name: medicineData.genericName || medicineData.salt,
                type: medicineData.type,
                distributor: medicineData.distributorName || medicineData.distributorCompany,
                purchase_price: medicineData.purchasedPrice,
                selling_price: medicineData.sellingPrice,
                stock_unit: medicineData.stockUnit,
                quantity: medicineData.quantity,
                expiration_date: medicineData.expiryDate,
                category: medicineData.category || '',
                sub_category: medicineData.subCategory || ''
            };

            this.pharmacyService.updateMedicineApi(this.medicineId, apiRequest).subscribe({
                next: (res) => {
                    this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Medicine updated successfully', life: 3000 });
                    // Update local state for immediate UI reflection
                    this.pharmacyService.update(this.medicineId!, medicineData);
                    this.cdr.markForCheck();
                    setTimeout(() => { this.router.navigate(['/staff/pharmacy/inventory']); }, 1500);
                },
                error: (err) => {
                    console.error('Failed to update medicine via API:', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update medicine', life: 4000 });
                }
            });
        } else {
            // Map form data to API request format
            const apiRequest = {
                product_id: parseInt(medicineData.productId || '0', 10),
                batch_no: medicineData.batchNumber,
                name: medicineData.name,
                generic_name: medicineData.genericName || medicineData.salt,
                type: medicineData.type,
                distributor: medicineData.distributorName || medicineData.distributorCompany,
                purchase_price: medicineData.purchasedPrice,
                selling_price: medicineData.sellingPrice,
                stock_unit: medicineData.stockUnit,
                quantity: medicineData.quantity,
                expiration_date: medicineData.expiryDate,
                category: medicineData.category || '',
                sub_category: medicineData.subCategory || ''
            };

            this.pharmacyService.addMedicineApi(apiRequest).subscribe({
                next: (res) => {
                    this.messageService.add({ severity: 'success', summary: 'Success', detail: 'Medicine added successfully', life: 3000 });
                    // Also update local state for immediate UI reflection if needed
                    this.pharmacyService.add(medicineData);
                    this.cdr.markForCheck();
                    setTimeout(() => { this.router.navigate(['/staff/pharmacy/inventory']); }, 1500);
                },
                error: (err) => {
                    console.error('Failed to add medicine via API:', err);
                    this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to add medicine to backend', life: 4000 });
                }
            });
        }
    }

    onCancel(): void { this.router.navigate(['/staff/pharmacy/inventory']); }

    formatDateForAPI(date: Date): string {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    isFieldInvalid(fieldName: string): boolean {
        const field = this.medicineForm.get(fieldName);
        return field ? field.invalid && (field.dirty || field.touched || this.submitted) : false;
    }
}