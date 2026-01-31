-- Convert relevance from array to single enum value (idempotent)
DO $$
BEGIN
  -- Only run if relevance is still an array type
  IF EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'extractions' 
    AND column_name = 'relevance' 
    AND data_type = 'ARRAY'
  ) THEN
    ALTER TABLE extractions ADD COLUMN relevance_new relevance;
    
    UPDATE extractions
    SET relevance_new = relevance[1]
    WHERE relevance IS NOT NULL AND array_length(relevance, 1) > 0;
    
    ALTER TABLE extractions DROP COLUMN relevance;
    ALTER TABLE extractions RENAME COLUMN relevance_new TO relevance;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_extractions_relevance;
CREATE INDEX IF NOT EXISTS idx_extractions_relevance ON extractions(relevance);
