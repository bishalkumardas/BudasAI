from supabase import create_client
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Safety check (recommended)
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials missing")

# Create client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)