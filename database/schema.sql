-- ============================================================================
-- BIRUKTAWIT FIKRE (@GIBDAW) WORKOUT BOT - LEAN 4-TABLE SCHEMA
-- ============================================================================

-- 1. Athletes / Profiles
CREATE TABLE IF NOT EXISTS athletes (
    telegram_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    username TEXT,
    gender VARCHAR(10),              -- 'FEMALE', 'MALE'
    age INT,
    weight_kg NUMERIC(5, 2),
    primary_goal VARCHAR(30),        -- 'BOOTY_CURVES', 'FAT_LOSS', 'MUSCLE_GAIN'
    days_per_week INT,               -- 3, 4
    experience_level VARCHAR(20),    -- 'BEGINNER', 'INTERMEDIATE'
    onboarding_state VARCHAR(50) DEFAULT 'START',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_interaction TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Workout Catalog
CREATE TABLE IF NOT EXISTS workout_catalog (
    sku VARCHAR(30) PRIMARY KEY,
    title TEXT NOT NULL,
    gender VARCHAR(10) NOT NULL,
    goal VARCHAR(30) NOT NULL,
    days_per_week INT NOT NULL,
    price_etb INT NOT NULL DEFAULT 950,
    pdf_path TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. Orders & Deliveries
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(30) PRIMARY KEY,
    athlete_id BIGINT NOT NULL REFERENCES athletes(telegram_id),
    sku VARCHAR(30) NOT NULL REFERENCES workout_catalog(sku),
    amount_etb INT NOT NULL,
    payment_method VARCHAR(20),       -- 'CBE', 'BOA', 'TELEBIRR'
    txn_ref VARCHAR(100) UNIQUE,      -- Prevents replay attacks
    receipt_file_id TEXT,
    recovery_sent BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'VERIFIED', 'REJECTED', 'DELIVERED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE
);

-- 4. Payout Ledger (60/40 for first 150 sales -> 70/30 permanently)
CREATE TABLE IF NOT EXISTS payout_ledger (
    payout_id VARCHAR(30) PRIMARY KEY,
    order_id VARCHAR(30) UNIQUE NOT NULL REFERENCES orders(order_id),
    sale_number INT NOT NULL,
    gross_amount INT NOT NULL,
    creator_share NUMERIC(10, 2) NOT NULL,
    platform_share NUMERIC(10, 2) NOT NULL,
    split_tier VARCHAR(20) NOT NULL,  -- 'TIER_1_60_40' or 'TIER_2_70_30'
    settlement_status VARCHAR(20) DEFAULT 'UNSETTLED',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Athlete Transformation Check-ins (Post-purchase 8-week progress tracking)
CREATE TABLE IF NOT EXISTS athlete_checkins (
    checkin_id SERIAL PRIMARY KEY,
    athlete_id BIGINT NOT NULL REFERENCES athletes(telegram_id),
    week_number INT NOT NULL,           -- Week 1 to 8
    weight_kg NUMERIC(5, 2) NOT NULL,
    workouts_completed INT NOT NULL,    -- 0 to 7
    notes TEXT,
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for lightning fast queries
CREATE INDEX IF NOT EXISTS idx_athletes_state ON athletes(onboarding_state);
CREATE INDEX IF NOT EXISTS idx_orders_athlete ON orders(athlete_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_payout_settlement ON payout_ledger(settlement_status);
CREATE INDEX IF NOT EXISTS idx_checkins_athlete ON athlete_checkins(athlete_id);

-- Seed core 12 workout catalog programs if not exists
INSERT INTO workout_catalog (sku, title, gender, goal, days_per_week, price_etb, pdf_path)
VALUES
    ('BF-F-BC-3X', '8-Week Booty & Curves (3x/Week)', 'FEMALE', 'BOOTY_CURVES', 3, 950, 'static/pdfs/BF_8W_F_Booty_3x.pdf'),
    ('BF-F-BC-4X', '8-Week Booty & Curves (4x/Week)', 'FEMALE', 'BOOTY_CURVES', 4, 950, 'static/pdfs/BF_8W_F_Booty_4x.pdf'),
    ('BF-F-FL-3X', '8-Week Fat Loss & Toning (3x/Week)', 'FEMALE', 'FAT_LOSS', 3, 950, 'static/pdfs/BF_8W_F_FatLoss_3x.pdf'),
    ('BF-F-FL-4X', '8-Week Fat Loss & Toning (4x/Week)', 'FEMALE', 'FAT_LOSS', 4, 950, 'static/pdfs/BF_8W_F_FatLoss_4x.pdf'),
    ('BF-F-MS-3X', '8-Week Full Body Definition (3x/Week)', 'FEMALE', 'MUSCLE_GAIN', 3, 950, 'static/pdfs/BF_8W_F_Muscle_3x.pdf'),
    ('BF-F-MS-4X', '8-Week Full Body Definition (4x/Week)', 'FEMALE', 'MUSCLE_GAIN', 4, 950, 'static/pdfs/BF_8W_F_Muscle_4x.pdf'),
    ('BF-M-MG-3X', '8-Week Upper/Lower Hypertrophy (3x/Week)', 'MALE', 'MUSCLE_GAIN', 3, 950, 'static/pdfs/BF_8W_M_Hypertrophy_3x.pdf'),
    ('BF-M-MG-4X', '8-Week Upper/Lower Hypertrophy (4x/Week)', 'MALE', 'MUSCLE_GAIN', 4, 950, 'static/pdfs/BF_8W_M_Hypertrophy_4x.pdf'),
    ('BF-M-FL-3X', '8-Week Fat Loss & Shred (3x/Week)', 'MALE', 'FAT_LOSS', 3, 950, 'static/pdfs/BF_8W_M_FatLoss_3x.pdf'),
    ('BF-M-FL-4X', '8-Week Fat Loss & Shred (4x/Week)', 'MALE', 'FAT_LOSS', 4, 950, 'static/pdfs/BF_8W_M_FatLoss_4x.pdf'),
    ('BF-M-ST-3X', '8-Week Strength & Power (3x/Week)', 'MALE', 'STRENGTH', 3, 950, 'static/pdfs/BF_8W_M_Strength_3x.pdf'),
    ('BF-M-ST-4X', '8-Week Strength & Power (4x/Week)', 'MALE', 'STRENGTH', 4, 950, 'static/pdfs/BF_8W_M_Strength_4x.pdf')
ON CONFLICT (sku) DO NOTHING;

