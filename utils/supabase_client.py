import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = None

# Path for storing session data
SESSION_FILE = Path(os.path.expanduser("~")) / ".hipot_session"

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
        
        # Try to restore session if available
        restore_session()
        
        return supabase
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        return None

def save_session(session):
    """Save session data to file for later retrieval"""
    try:
        session_data = {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(session_data, f)
        print("Session saved successfully")
    except Exception as e:
        print(f"Error saving session: {e}")

def restore_session():
    """Try to restore a previously saved session"""
    global supabase
    if not supabase:
        return False
        
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, "r") as f:
                session_data = json.load(f)
                
            # Set the session in the client
            supabase.auth.set_session(
                session_data.get("access_token", ""),
                session_data.get("refresh_token", "")
            )
            
            # Check if session is still valid
            user = supabase.auth.get_user()
            if user:
                print(f"Session restored for user: {user.user.email}")
                return True
            else:
                print("Stored session expired")
                clear_session()
                return False
                
    except Exception as e:
        print(f"Error restoring session: {e}")
        # Clean up any potentially corrupt session file
        clear_session()
        return False
    
    return False

def clear_session():
    """Remove saved session data"""
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
            print("Session data cleared")
    except Exception as e:
        print(f"Error clearing session: {e}")

def get_current_user():
    """Get the currently authenticated user, if any"""
    global supabase
    if not supabase:
        return None
        
    try:
        response = supabase.auth.get_user()
        return response.user if response else None
    except Exception:
        return None 