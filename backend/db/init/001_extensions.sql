-- kAIkei database initialization
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable Row Level Security
SET default_row_level_security = on;
