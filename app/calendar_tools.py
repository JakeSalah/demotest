import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
# FastMCP will automatically expose the FastAPI routes as tools
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from .auth import create_service, get_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

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
def get_calendar_service():
    """Get an authenticated Google Calendar service."""
    try:
        service = create_service("calendar", "v3")
        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate with Google Calendar. Please check your credentials."
            )
        return service
    except Exception as e:
        logger.error(f"Error creating calendar service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Google Calendar service: {str(e)}"
        )

# MCP Tools
@router.get("/events", response_model=List[Dict[str, Any]])
def list_events(max_results: int = 10):
    """List the next N events from the primary calendar."""
    try:
        service = get_calendar_service()
        now = datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except HttpError as error:
        raise HTTPException(status_code=500, detail=f"An error occurred: {error}")

@router.get("/events", response_model=List[Dict[str, Any]])
def list_events_route(max_results: int = 10) -> List[Dict[str, Any]]:
    """List upcoming calendar events.
    
    Args:
        max_results: Maximum number of events to return (default: 10)
    """
    return list_events(max_results)

# FastMCP will automatically expose the FastAPI route as a tool

@router.post("/events", response_model=Dict[str, Any])
def create_event_route(event: CalendarEvent) -> Dict[str, Any]:
    """Create a new calendar event."""
    try:
        service = get_calendar_service()
        
        # Convert the Pydantic model to a dictionary
        event_dict = event.dict()
        
        # Ensure required fields are present
        if 'start' not in event_dict or 'end' not in event_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start and end times are required"
            )
        
        # Create the event
        created_event = service.events().insert(
            calendarId='primary',
            body=event_dict
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
        
        return updated_event
    except HttpError as error:
        if error.resp.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        raise HTTPException(status_code=500, detail=f"An error occurred: {error}")

# FastMCP will automatically expose the FastAPI route as a tool

@router.delete("/events/{event_id}")
def delete_event_route(event_id: str) -> Dict[str, str]:
    """Delete a calendar event."""
    try:
        service = get_calendar_service()
        
        # Check if the event exists
        service.events().get(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        # Delete the event
        service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        return {"status": "Event deleted successfully"}
    except HttpError as error:
        if error.resp.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        raise HTTPException(status_code=500, detail=f"An error occurred: {error}")

# FastMCP will automatically expose the FastAPI route as a tool
