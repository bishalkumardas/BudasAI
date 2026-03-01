from supabase import create_client
import os
from dotenv import load_dotenv
import sys

# Load .env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Safety check (recommended)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: SUPABASE_URL and SUPABASE_KEY environment variables are required")
    print("Please set them in your Railway dashboard or .env file")
    sys.exit(1)

print("✅ Supabase credentials loaded successfully")

# Create client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)