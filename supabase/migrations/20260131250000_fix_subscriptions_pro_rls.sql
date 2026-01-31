-- Fix RLS policy to explicitly allow anon and authenticated roles
DROP POLICY IF EXISTS "Allow anonymous insert" ON public.subscriptions_pro;

CREATE POLICY "Allow anonymous inserts" ON public.subscriptions_pro
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

