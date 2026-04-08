-- PulseQ Database Schema for PostgreSQL/Supabase
-- Run these SQL statements in Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 1. USERS TABLE
-- ==========================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'patient',
    location_access BOOLEAN DEFAULT FALSE,
    date_of_birth VARCHAR(20),
    address VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);

-- ==========================================
-- 2. HOSPITALS TABLE
-- ==========================================
CREATE TABLE hospitals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    address VARCHAR(500) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(255),
    rating FLOAT,
    review_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'open',
    specializations JSONB DEFAULT '[]',
    latitude FLOAT,
    longitude FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. DOCTORS TABLE
-- ==========================================
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    specialization VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(255),
    experience_years INTEGER DEFAULT 0,
    rating FLOAT,
    review_count INTEGER DEFAULT 0,
    consultation_fee FLOAT NOT NULL,
    session_fee FLOAT,
    has_session BOOLEAN DEFAULT FALSE,
    pricing_type VARCHAR(20) DEFAULT 'standard',
    status VARCHAR(20) DEFAULT 'available',
    available_days JSONB DEFAULT '[]',
    start_time VARCHAR(10) NOT NULL,
    end_time VARCHAR(10) NOT NULL,
    avatar_initials VARCHAR(10),
    patients_per_day INTEGER DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_doctors_hospital_id ON doctors(hospital_id);
CREATE INDEX idx_doctors_specialization ON doctors(specialization);

-- ==========================================
-- 4. TOKENS TABLE
-- ==========================================
CREATE TABLE tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    mrn VARCHAR(50),
    token_number INTEGER NOT NULL,
    hex_code VARCHAR(10) NOT NULL,
    display_code VARCHAR(20),
    appointment_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    payment_status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(20),
    queue_position INTEGER,
    total_queue INTEGER,
    estimated_wait_time INTEGER,
    consultation_fee FLOAT,
    session_fee FLOAT,
    total_fee FLOAT,
    department VARCHAR(100),
    idempotency_key VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Embedded snapshots
    doctor_name VARCHAR(100),
    doctor_specialization VARCHAR(100),
    doctor_avatar_initials VARCHAR(10),
    hospital_name VARCHAR(200)
);

CREATE INDEX idx_tokens_patient_id ON tokens(patient_id);
CREATE INDEX idx_tokens_doctor_id ON tokens(doctor_id);
CREATE INDEX idx_tokens_hospital_id ON tokens(hospital_id);
CREATE INDEX idx_tokens_status ON tokens(status);

-- ==========================================
-- 5. PAYMENTS TABLE
-- ==========================================
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_id UUID NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
    amount FLOAT NOT NULL,
    method VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    transaction_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payments_token_id ON payments(token_id);

-- ==========================================
-- 6. ACTIVITY LOGS TABLE
-- ==========================================
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    meta_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_activity_logs_user_id ON activity_logs(user_id);

-- ==========================================
-- 7. QUEUES TABLE
-- ==========================================
CREATE TABLE queues (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    current_token INTEGER,
    waiting_patients INTEGER DEFAULT 0,
    estimated_wait_time_minutes INTEGER,
    people_ahead INTEGER DEFAULT 0,
    total_queue INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_queues_doctor_id ON queues(doctor_id);

-- ==========================================
-- 8. IDEMPOTENCY RECORDS TABLE
-- ==========================================
CREATE TABLE idempotency_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    key VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    token_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_idempotency_user_key ON idempotency_records(user_id, key);

-- ==========================================
-- 9. PHARMACY MEDICINES TABLE
-- ==========================================
CREATE TABLE pharmacy_medicines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id INTEGER NOT NULL,
    batch_no VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    generic_name VARCHAR(200),
    type VARCHAR(100),
    distributor VARCHAR(200),
    purchase_price FLOAT NOT NULL,
    selling_price FLOAT NOT NULL,
    stock_unit VARCHAR(50),
    quantity INTEGER DEFAULT 0,
    expiration_date TIMESTAMP WITH TIME ZONE,
    category VARCHAR(100),
    sub_category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pharmacy_medicines_name ON pharmacy_medicines(name);
CREATE INDEX idx_pharmacy_medicines_product_id ON pharmacy_medicines(product_id);

-- ==========================================
-- 10. DEPARTMENTS TABLE
-- ==========================================
CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_departments_hospital_id ON departments(hospital_id);

-- ==========================================
-- INSERT SAMPLE DATA (Optional)
-- ==========================================

-- Sample Hospital
INSERT INTO hospitals (name, address, city, state, phone, email, rating, status)
VALUES (
    'PulseQ General Hospital',
    '123 Main Street, Gulberg',
    'Lahore',
    'Punjab',
    '+9203123456789',
    'info@pulseq.com',
    4.5,
    'open'
);

-- Sample Departments
INSERT INTO departments (name, hospital_id) VALUES
('Cardiology', (SELECT id FROM hospitals LIMIT 1)),
('Neurology', (SELECT id FROM hospitals LIMIT 1)),
('Pediatrics', (SELECT id FROM hospitals LIMIT 1)),
('Orthopedics', (SELECT id FROM hospitals LIMIT 1)),
('General Medicine', (SELECT id FROM hospitals LIMIT 1));

-- Sample Doctor
INSERT INTO doctors (
    name, specialization, hospital_id, phone, email, 
    experience_years, consultation_fee, start_time, end_time, status
) VALUES (
    'Dr. Ahmad Khan',
    'Cardiology',
    (SELECT id FROM hospitals LIMIT 1),
    '+9203123456790',
    'dr.ahmad@pulseq.com',
    15,
    2000,
    '09:00',
    '17:00',
    'available'
);

-- ==========================================
-- TABLE INFORMATION QUERIES
-- ==========================================

-- Get all tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Get columns for a specific table (example: users)
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;

-- ==========================================
-- 11. ACTIVITIES TABLE (Additional)
-- ==========================================
CREATE TABLE activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    meta_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_activities_user_id ON activities(user_id);

-- ==========================================
-- 12. APPOINTMENTS TABLE
-- ==========================================
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    token_id UUID REFERENCES tokens(id) ON DELETE SET NULL,
    appointment_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_appointments_patient_id ON appointments(patient_id);
CREATE INDEX idx_appointments_doctor_id ON appointments(doctor_id);

-- ==========================================
-- 13. CAPACITY TABLE
-- ==========================================
CREATE TABLE capacity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    max_patients INTEGER DEFAULT 10,
    booked_patients INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doctor_id, hospital_id, date)
);

CREATE INDEX idx_capacity_doctor_id ON capacity(doctor_id);

-- ==========================================
-- 14. COUNTERS TABLE
-- ==========================================
CREATE TABLE counters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    current_number INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_counters_hospital_id ON counters(hospital_id);

-- ==========================================
-- 15. IDEMPOTENCY TABLE (Alternative naming)
-- ==========================================
CREATE TABLE idempotency (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    key VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    token_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);

CREATE INDEX idx_idempotency_user_key_2 ON idempotency(user_id, key);

-- ==========================================
-- 16. PHARMACY ITEMS TABLE
-- ==========================================
CREATE TABLE pharmacy_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    generic_name VARCHAR(200),
    category VARCHAR(100),
    type VARCHAR(100),
    unit VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pharmacy_items_name ON pharmacy_items(name);

-- ==========================================
-- 17. PHARMACY PRESCRIPTIONS TABLE
-- ==========================================
CREATE TABLE pharmacy_prescriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    token_id UUID REFERENCES tokens(id) ON DELETE SET NULL,
    prescription_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    medicines JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pharmacy_prescriptions_patient_id ON pharmacy_prescriptions(patient_id);
CREATE INDEX idx_pharmacy_prescriptions_doctor_id ON pharmacy_prescriptions(doctor_id);

-- ==========================================
-- 18. PHARMACY SALES TABLE
-- ==========================================
CREATE TABLE pharmacy_sales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prescription_id UUID REFERENCES pharmacy_prescriptions(id) ON DELETE SET NULL,
    patient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_amount FLOAT NOT NULL,
    discount FLOAT DEFAULT 0,
    final_amount FLOAT NOT NULL,
    payment_method VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pharmacy_sales_patient_id ON pharmacy_sales(patient_id);

-- ==========================================
-- 19. PHARMACY STOCK LOGS TABLE
-- ==========================================
CREATE TABLE pharmacy_stock_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    medicine_id UUID NOT NULL REFERENCES pharmacy_medicines(id) ON DELETE CASCADE,
    quantity_change INTEGER NOT NULL,
    reason VARCHAR(255),
    reference_id UUID,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pharmacy_stock_logs_medicine_id ON pharmacy_stock_logs(medicine_id);

-- ==========================================
-- 20. QUICK ACTIONS TABLE
-- ==========================================
CREATE TABLE quick_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    icon VARCHAR(100),
    route VARCHAR(255),
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quick_actions_user_id ON quick_actions(user_id);

-- ==========================================
-- GET ALL TABLES INFO
-- ==========================================

-- Get all tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Get columns for a specific table (example: users)
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;

-- Get all foreign keys
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';
