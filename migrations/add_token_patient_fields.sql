-- =====================================================
-- CRITICAL: Add Missing Patient Fields to Tokens Table
-- Run this in pgAdmin Query Tool
-- =====================================================

-- Check if columns exist first
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tokens' 
  AND column_name IN ('patient_age', 'patient_gender', 'reason_for_visit')
ORDER BY column_name;

-- If the above query returns 0 rows, run these ALTER statements:

-- Add patient_age column
ALTER TABLE tokens 
ADD COLUMN IF NOT EXISTS patient_age INTEGER;

-- Add patient_gender column  
ALTER TABLE tokens 
ADD COLUMN IF NOT EXISTS patient_gender VARCHAR(20);

-- Add reason_for_visit column
ALTER TABLE tokens 
ADD COLUMN IF NOT EXISTS reason_for_visit TEXT;

-- Verify columns were added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'tokens'
  AND column_name IN ('patient_age', 'patient_gender', 'reason_for_visit')
ORDER BY column_name;

-- Test: Check a sample token
SELECT 
    id,
    token_number,
    patient_name,
    patient_age,
    patient_gender,
    reason_for_visit
FROM tokens
LIMIT 5;
