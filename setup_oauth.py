"""
Script to help set up OAuth 2.0 for Google Calendar API.
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Use a fixed port for the OAuth callback
REDIRECT_URI = 'http://localhost:3000/oauth'

def main():
    creds = None
    
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception as e:
            print(f"❌ Error loading token: {e}")
            print("Removing invalid token file...")
            os.remove('token.json')
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("✅ Successfully refreshed token")
            except Exception as e:
                print(f"❌ Error refreshing token: {e}")
                print("Please re-authenticate...")
                creds = None
        
        if not creds:
            if not os.path.exists('credentials.json'):
                print('❌ Error: credentials.json not found.')
                print('Please download your OAuth 2.0 client ID from Google Cloud Console')
                print('and save it as credentials.json in this directory.')
                return
            
            try:
                # Load the client config from the file
                with open('credentials.json', 'r') as f:
                    client_config = json.load(f)
                
                # Ensure the redirect URI is set correctly
                if 'web' in client_config and 'redirect_uris' in client_config['web']:
                    if REDIRECT_URI not in client_config['web']['redirect_uris']:
                        client_config['web']['redirect_uris'].append(REDIRECT_URI)
                
                # Create the flow using the client config
                flow = InstalledAppFlow.from_client_config(
                    client_config,
                    scopes=SCOPES,
                    redirect_uri=REDIRECT_URI
                )
                
                # Run the local server flow
                creds = flow.run_local_server(port=3000, open_browser=True)
                
                # Save the credentials for the next run
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                print('✅ Successfully saved credentials to token.json')
                
            except Exception as e:
                print(f"❌ Error during OAuth flow: {e}")
                return
    else:
        print('✅ Already authenticated with Google Calendar API')
    
    # Print the token info
    if creds:
        print("\nToken information:")
        print(f"- Token: {'...' + creds.token[-10:] if creds.token else 'None'}")
        print(f"- Expires: {creds.expiry}" if creds.expiry else "- No expiry")
        print(f"- Scopes: {creds.scopes}" if creds.scopes else "- No scopes")
        print(f"- Refresh token: {'Yes' if creds.refresh_token else 'No'}")

if __name__ == '__main__':
    main()
