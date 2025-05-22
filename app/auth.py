"""
Authentication utilities for Google MCPs
"""

import base64
import json
import os
from typing import List, Any, Optional
import logging
from pathlib import Path
from googleapiclient.discovery import build

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Default scopes for Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# File paths
ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = os.environ.get('TOKEN_PATH', str(ROOT / 'token.json'))
CREDENTIALS_PATH = os.environ.get('CREDENTIALS_PATH', str(ROOT / 'credentials.json'))
SERVICE_ACCOUNT_PATH = os.environ.get('SERVICE_ACCOUNT_PATH', str(ROOT / 'service_account.json'))

def get_credentials(scopes: List[str] = None) -> Any:
    """
    Get OAuth credentials using various methods.
    
    Tries in this order:
    1. Use base64 encoded credentials from CREDENTIALS_CONFIG env var
    2. Use service account file from SERVICE_ACCOUNT_PATH env var
    3. Use OAuth flow from CREDENTIALS_PATH/TOKEN_PATH
    
    Args:
        scopes: List of OAuth scopes needed (defaults to SCOPES)
        
    Returns:
        Google Auth credentials object or None if all auth methods fail
    """
    if scopes is None:
        scopes = SCOPES
        
    creds = None
    
    # 1. Try credentials from environment var (base64 encoded)
    credentials_config = os.environ.get('CREDENTIALS_CONFIG')
    if credentials_config:
        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(base64.b64decode(credentials_config)), scopes)
            logger.info("Using credentials from CREDENTIALS_CONFIG environment variable")
            return creds
        except Exception as e:
            logger.warning(f"Failed to load credentials from CREDENTIALS_CONFIG: {e}")
    
    # 2. Try service account auth
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        try:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_PATH, scopes=scopes)
            logger.info(f"Using service account authentication from {SERVICE_ACCOUNT_PATH}")
            return creds
        except Exception as e:
            logger.warning(f"Service account auth failed: {e}")
    
    # 3. Try OAuth flow with saved token
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, "r") as tf:
                creds = Credentials.from_authorized_user_info(json.load(tf), scopes)
            logger.info(f"Loaded OAuth credentials from {TOKEN_PATH}")
        except Exception as e:
            logger.warning(f"Failed to load OAuth token: {e}")
    
    # 4. Refresh token if expired or get new tokens
    try:
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logger.info("Refreshed OAuth token")
            else:
                # Interactive OAuth flow - requires browser
                if not os.path.exists(CREDENTIALS_PATH):
                    logger.error(f"OAuth credentials not found at {CREDENTIALS_PATH}")
                    return None
                    
                # Create flow with specific redirect URI
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, 
                    scopes=scopes,
                    redirect_uri="http://localhost:8080"
                )
                # Run the server on port 8080 to match the redirect URI
                creds = flow.run_local_server(port=8080)
                logger.info("Completed OAuth flow with browser sign-in")
            
            # Save the credentials for next run
            try:
                with open(TOKEN_PATH, "w") as tf:
                    tf.write(creds.to_json())
                logger.info(f"Saved OAuth credentials to {TOKEN_PATH}")
            except Exception as e:
                logger.warning(f"Failed to save OAuth token: {e}")
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None
        
    return creds

def create_service(api_name: str, api_version: str, scopes: List[str] = None) -> Optional[Any]:
    """
    Create a Google API service with proper authentication.
    
    Args:
        api_name: Name of the Google API (e.g., 'drive', 'sheets')
        api_version: API version (e.g., 'v3')
        scopes: List of OAuth scopes needed (defaults to SCOPES)
        
    Returns:
        Google API service or None if authentication fails
    """
    if scopes is None:
        scopes = SCOPES
        
    creds = get_credentials(scopes)
    if not creds:
        logger.error(f"Failed to get valid credentials for {api_name}")
        return None
        
    try:
        service = build(api_name, api_version, credentials=creds)
        logger.info(f"Created {api_name} service")
        return service
    except Exception as e:
        logger.error(f"Failed to create {api_name} service: {e}")
        return None

# For backward compatibility
def init_oauth_flow() -> None:
    """Initialize the OAuth 2.0 flow with user-friendly instructions."""
    print("Initializing Google OAuth 2.0 flow...")
    print("Make sure you have set up the following in Google Cloud Console:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Select your project")
    print("3. Navigate to 'APIs & Services' > 'Credentials'")
    print("4. Add 'http://localhost:8080' to 'Authorized redirect URIs'")
    print("\nStarting OAuth flow...")
    
    creds = get_credentials()
    if creds:
        print("\n✅ Authentication successful! Credentials have been saved to token.json")
        print("You can now start the server with: python3 -m uvicorn main:app --reload")
    else:
        print("\n❌ Authentication failed. Please check the error messages above and try again.")
        print("Make sure your credentials.json is properly configured and the redirect URI is allowed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize Google OAuth 2.0 flow")
    parser.add_argument("--init", action="store_true", help="Initialize OAuth flow")
    args = parser.parse_args()
    
    if args.init:
        init_oauth_flow()
    else:
        print("Use --init to start the OAuth flow")
