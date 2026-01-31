-- Create subscriptions table for email alerts
CREATE TABLE public.subscriptions (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  sectors sector[] DEFAULT '{}',
  relevance_threshold relevance DEFAULT 'medium',
  keywords TEXT[] DEFAULT '{}',
  is_verified BOOLEAN DEFAULT FALSE,
  verification_token UUID DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  unsubscribed_at TIMESTAMPTZ DEFAULT NULL,
  
  CONSTRAINT subscriptions_email_unique UNIQUE (email)
);

-- Index for faster lookups
CREATE INDEX idx_subscriptions_email ON public.subscriptions(email);
CREATE INDEX idx_subscriptions_verified ON public.subscriptions(is_verified) WHERE is_verified = TRUE AND unsubscribed_at IS NULL;

-- RLS policies
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

-- Allow anonymous inserts (for signup)
CREATE POLICY "Allow anonymous insert" ON public.subscriptions
  FOR INSERT
  WITH CHECK (true);

-- Comment
COMMENT ON TABLE public.subscriptions IS 'Email subscriptions for hearing alerts';

