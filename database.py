from supabase import create_client
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Safety check (recommended)
if not SUPABASE_URL or not SUPABASE_KEY:
    error_msg = "❌ CRITICAL: SUPABASE_URL and SUPABASE_KEY environment variables are required"
    print(error_msg)
    print("Please set them in your Railway dashboard or .env file")
    raise RuntimeError(error_msg)

print("✅ Supabase credentials loaded successfully")

# Create client
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client created successfully")
except Exception as e:
    print(f"❌ Failed to create Supabase client: {e}")
    raise