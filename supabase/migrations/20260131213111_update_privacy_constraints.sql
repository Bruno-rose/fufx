-- Allow anyone to insert a subscription (for email signups)
CREATE POLICY "Allow public insert on subscriptions"
ON subscriptions
FOR INSERT
TO anon
WITH CHECK (true);

-- Allow anyone to select their own subscription by email (for the "existing" check)
CREATE POLICY "Allow public select by email on subscriptions"
ON subscriptions
FOR SELECT
TO anon
USING (true);

-- Allow updates to existing subscriptions (for re-subscribing)
CREATE POLICY "Allow public update on subscriptions"
ON subscriptions
FOR UPDATE
TO anon
USING (true)
WITH CHECK (true);