ALTER TABLE subscriptions_pro ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for anon" ON subscriptions_pro
FOR ALL TO anon
USING (true)
WITH CHECK (true);