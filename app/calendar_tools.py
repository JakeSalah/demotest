import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from pydantic import BaseModel
import os
import json
import jwt
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

SCOPES = ['https://www.googleapis.com/auth/calendar']

# JWT Configuration
SECRET_KEY = os.getenv('JWT_SECRET', 'your-secret-key')
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_flow():
    return Flow.from_client_secrets_file(
        os.getenv('CREDENTIALS_PATH', 'credentials.json'),
        scopes=SCOPES,
        redirect_uri=os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/calendar/auth/callback')
    )

@router.get("/auth")
async def auth():
    """Generate Google OAuth2 URL for authentication"""
    try:
        flow = get_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )
        return {"auth_url": auth_url}
    except Exception as e:
        logging.error(f"Error generating auth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate authentication URL"
        )

class CallbackData(BaseModel):
    code: str

@router.get("/auth/callback")
async def callback(code: str):
    """Exchange authorization code for tokens"""
    try:
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authorization code is required"
            )
            
        flow = get_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        # Save the credentials
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        with open('token.json', 'w') as token:
            token.write(json.dumps(creds_data))
        return {"status": "success", "message": "Successfully authenticated"}
    except Exception as e:
        logging.error(f"Error in callback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

def get_google_credentials():
    """Get Google credentials from token file"""
    if not os.path.exists('token.json'):
        return None
    with open('token.json', 'r') as token:
        creds_info = json.load(token)
    return Credentials(
        token=creds_info['token'],
        refresh_token=creds_info.get('refresh_token'),
        token_uri=creds_info['token_uri'],
        client_id=creds_info['client_id'],
        client_secret=creds_info['client_secret'],
        scopes=creds_info['scopes']
    )

# Pydantic models for request/response validation
class EventTime(BaseModel):
    dateTime: str
    timeZone: str = "UTC"

class Event(BaseModel):
    summary: str
    description: Optional[str] = None
    start: EventTime
    end: EventTime
    attendees: Optional[List[Dict[str, str]]] = None
    reminders: Optional[Dict[str, Any]] = None

class CalendarEvent(BaseModel):
    summary: str
    description: Optional[str] = None
    start: str  # ISO 8601 datetime string
    end: str    # ISO 8601 datetime string
    timezone: str = "UTC"
    attendees: Optional[List[str]] = None

# Helper function to get Google Calendar service
def get_calendar_service(token: str = Depends(oauth2_scheme)):
    """Get an authenticated Google Calendar service."""
    try:
        # Verify JWT token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials"
                )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        # Get Google credentials
        credentials = get_google_credentials()
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated with Google"
            )
        # Refresh token if expired
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        # Build the service
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error creating calendar service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Google Calendar service: {str(e)}"
        )

# MCP Tools
@router.get("/events", response_model=List[Dict[str, Any]])
def list_events(token: str = Depends(oauth2_scheme)):
    """List the next N events from the primary calendar."""
    try:
        service = get_calendar_service(token)
        now = datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except HttpError as error:
        raise HTTPException(status_code=500, detail=f"An error occurred: {error}")

@router.post("/events", response_model=Dict[str, Any])
def create_event_route(event: CalendarEvent, token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Create a new calendar event."""
    try:
        service = get_calendar_service(token)
        
        # Convert the Pydantic model to a dictionary
        event_dict = event.dict()
        
        # Ensure required fields are present
        if 'start' not in event_dict or 'end' not in event_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start and end times are required"
            )
        
        # Format the event data for Google Calendar API
        google_event = {
            'summary': event.summary,
            'description': event.description,
            'start': {
                'dateTime': event.start,
                'timeZone': event.timezone
            },
            'end': {
                'dateTime': event.end,
                'timeZone': event.timezone
            }
        }
        
        # Add attendees if present
        if event.attendees:
            google_event['attendees'] = [{'email': email} for email in event.attendees]
        
        # Create the event
        created_event = service.events().insert(
            calendarId='primary',
            body=google_event
        ).execute()
        
        return created_event
    except HttpError as error:
        raise HTTPException(status_code=500, detail=f"An error occurred: {error}")

# FastMCP will automatically expose the FastAPI route as a tool

@router.patch("/events/{event_id}", response_model=Dict[str, Any])
def update_event_route(event_id: str, event: CalendarEvent) -> Dict[str, Any]:
    """Update an existing calendar event."""
    try:
        service = get_calendar_service()
        
        # Get the existing event to ensure it exists
        existing_event = service.events().get(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        if not existing_event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        
        # Update the event with the new data
        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body={
                **existing_event,
                **event.dict(exclude_unset=True)
            }
        ).execute()
        
        return {
            "status": "success",
            "message": "Event updated successfully",
            "event_id": event_id,
            "updated_fields": event.dict(exclude_unset=True)
        }
        
    except HttpError as error:
        error_detail = f"Google API error: {error._get_reason()}"
        logger.error(f"Error updating event {event_id}: {error_detail}")
        
        if error.resp.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "error",
                    "code": "event_not_found",
                    "message": "The specified event was not found"
                }
            )
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "code": "update_failed",
                "message": "Failed to update event",
                "details": error_detail
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error in update_event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "code": "internal_server_error",
                "message": "An unexpected error occurred"
            }
        )

@router.delete(
    "/events/{event_id}",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Event deleted successfully"},
        404: {"description": "Event not found"},
        500: {"description": "Internal server error"}
    }
)
async def delete_event_route(
    event_id: str
) -> Dict[str, Any]:
    """
    Delete a calendar event by ID.
    
    Args:
        event_id: The ID of the event to delete
        current_user: The authenticated user (from JWT token)
        
    Returns:
        Dict containing status and message
    """
    try:
        logger.info(f"Attempting to delete event {event_id}")
        service = get_calendar_service()
        
        # Check if the event exists
        event = service.events().get(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        # Delete the event
        service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        logger.info(f"Successfully deleted event {event_id}")
        return {
            "status": "success",
            "message": "Event deleted successfully",
            "event_id": event_id,
            "deleted_at": datetime.utcnow().isoformat()
        }
        
    except HttpError as error:
        error_detail = f"Google API error: {error._get_reason()}"
        logger.error(f"Error deleting event {event_id}: {error_detail}")
        
        if error.resp.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "error",
                    "code": "event_not_found",
                    "message": "The specified event was not found"
                }
            )
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "code": "delete_failed",
                "message": "Failed to delete event",
                "details": error_detail
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in delete_event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "code": "internal_server_error",
                "message": "An unexpected error occurred"
            }
        )
