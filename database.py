from supabase import create_client
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY")
)

# Safety check (recommended)
if not SUPABASE_URL or not SUPABASE_KEY:
    error_msg = "❌ CRITICAL: SUPABASE_URL and SUPABASE_KEY environment variables are required"
    print(error_msg)
    print("Please set them in your Railway dashboard or .env file")
    raise RuntimeError(error_msg)

print("✅ Supabase credentials loaded successfully")
if os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY"):
    print("✅ Using Supabase service-role key for server operations")
else:
    print("⚠️ Using SUPABASE_KEY fallback. Set SUPABASE_SERVICE_ROLE_KEY for reliable server-side writes.")

# Create client
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client created successfully")
except Exception as e:
    print(f"❌ Failed to create Supabase client: {e}")
    raise