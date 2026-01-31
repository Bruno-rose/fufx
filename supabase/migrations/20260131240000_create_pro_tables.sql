-- Create frequency enum for digest scheduling
DO $$ BEGIN
    CREATE TYPE digest_frequency AS ENUM (
        'daily',
        'weekly',
        'monthly'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Pro subscriptions table
CREATE TABLE IF NOT EXISTS public.subscriptions_pro (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    company_type TEXT,  -- e.g. 'pharma', 'biotech', 'medtech'
    keywords TEXT[] DEFAULT '{}',
    is_verified BOOLEAN DEFAULT FALSE,
    verification_token UUID DEFAULT gen_random_uuid(),
    frequency digest_frequency DEFAULT 'weekly',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    unsubscribed_at TIMESTAMPTZ DEFAULT NULL,

    CONSTRAINT subscriptions_pro_email_unique UNIQUE (email)
);

CREATE INDEX idx_subscriptions_pro_email ON public.subscriptions_pro(email);
CREATE INDEX idx_subscriptions_pro_verified ON public.subscriptions_pro(is_verified) 
    WHERE is_verified = TRUE AND unsubscribed_at IS NULL;

-- Pro extractions table (personalized digests)
CREATE TABLE IF NOT EXISTS public.extractions_pro (
    id SERIAL PRIMARY KEY,
    subscription_pro_id INTEGER NOT NULL REFERENCES subscriptions_pro(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    period_date DATE NOT NULL,  -- which digest period this belongs to
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ DEFAULT NULL,

    -- Prevent duplicate entries for same subscription/document/period
    UNIQUE(subscription_pro_id, document_id, period_date)
);

CREATE INDEX idx_extractions_pro_subscription ON public.extractions_pro(subscription_pro_id);
CREATE INDEX idx_extractions_pro_document ON public.extractions_pro(document_id);
CREATE INDEX idx_extractions_pro_period ON public.extractions_pro(period_date);
CREATE INDEX idx_extractions_pro_unsent ON public.extractions_pro(subscription_pro_id, period_date) 
    WHERE sent_at IS NULL;

-- RLS
ALTER TABLE public.subscriptions_pro ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extractions_pro ENABLE ROW LEVEL SECURITY;

-- Allow anonymous inserts for signup
CREATE POLICY "Allow anonymous insert" ON public.subscriptions_pro
    FOR INSERT
    WITH CHECK (true);

COMMENT ON TABLE public.subscriptions_pro IS 'Pro email subscriptions with company-specific digests';
COMMENT ON TABLE public.extractions_pro IS 'Personalized extraction summaries for pro subscribers';

