-- Set all existing subscriptions as verified and change default to TRUE
UPDATE public.subscriptions SET is_verified = TRUE WHERE is_verified = FALSE;
UPDATE public.subscriptions_pro SET is_verified = TRUE WHERE is_verified = FALSE;

ALTER TABLE public.subscriptions ALTER COLUMN is_verified SET DEFAULT TRUE;
ALTER TABLE public.subscriptions_pro ALTER COLUMN is_verified SET DEFAULT TRUE;

