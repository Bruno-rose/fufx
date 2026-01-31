-- Extend sector enum with new values used by extraction prompt
ALTER TYPE sector ADD VALUE IF NOT EXISTS 'aerospace';
ALTER TYPE sector ADD VALUE IF NOT EXISTS 'agriculture';
ALTER TYPE sector ADD VALUE IF NOT EXISTS 'education';
ALTER TYPE sector ADD VALUE IF NOT EXISTS 'environment';
