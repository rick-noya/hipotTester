import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = None

def get_supabase_client():
    """Initializes and returns the Supabase client. Returns None if credentials are missing."""
    global supabase
    if supabase:
        return supabase

    if not url or not key:
        print("Warning: SUPABASE_URL and SUPABASE_KEY environment variables not set. Supabase logging disabled.")
        return None

    try:
        supabase = create_client(url, key)
        print("Supabase client initialized successfully.")
        return supabase
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        return None 