import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
# MCP is now imported from fastmcp
from fastapi.security.utils import get_authorization_scheme_param
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response
from fastmcp import FastMCP
import uvicorn

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Token model
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None

# User model
class User(BaseModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    disabled: Union[bool, None] = None

class UserInDB(User):
    hashed_password: str

# Mock user database
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "disabled": False,
        "hashed_password": pwd_context.hash("testpassword")
    }
}

def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)

def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not pwd_context.verify(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for public endpoints
        public_paths = ["/healthz", "/docs", "/openapi.json", "/token"]
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)
            
        # Get token from Authorization header
        authorization: str = request.headers.get("Authorization")
        if not authorization:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        scheme, token = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        try:
            # Verify token
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=400, detail="Invalid token")
            
            # Add user to request state
            request.state.user = get_user(fake_users_db, username)
            
        except JWTError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return await call_next(request)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app with CORS middleware only
app = FastAPI(
    title="Google Calendar MCP Server",
    description="MCP server for Google Calendar integration",
    version="1.0.0",
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"]
        )
    ]
)

# Token endpoint for authentication
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Import and include routers
from app import calendar_tools, auth

# Include the calendar router with its prefix
app.include_router(calendar_tools.router, prefix="")

# Initialize FastMCP after all routes are defined
mcp = FastMCP.from_fastapi(app)

# Health check endpoint
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# Test endpoint to verify SSE connection
@app.get("/test-sse")
async def test_sse():
    """Test endpoint that returns a single SSE message and closes the connection."""
    async def event_generator():
        test_message = {
            "message": "Test successful",
            "status": "connected",
            "endpoint": "/stream"
        }
        yield f"data: {json.dumps(test_message)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

# MCP server is already initialized above

# MCP endpoints
@app.post("/messages")
async def handle_messages(request: Request):
    """Handle JSON-RPC messages."""
    data = await request.json()
    return await mcp.dispatch(data)

# HTTP Streamable endpoint for n8n MCP Client Tool
@app.post("/stream")
@app.get("/stream")  # Support both GET and POST
async def stream_endpoint(request: Request):
    """HTTP Streamable endpoint for n8n MCP Client Tool.
    
    This endpoint implements both SSE and HTTP Streamable protocols for MCP.
    """
    # Check if client accepts text/event-stream (SSE) or application/x-ndjson (HTTP Streamable)
    accept = request.headers.get("accept", "")
    is_sse = "text/event-stream" in accept
    
    async def event_generator():
        try:
            # Initial handshake
            handshake = {
                "type": "handshake",
                "data": {
                    "endpoint": "/messages",
                    "auth": {"type": "none"},
                    "protocol": "http-streamable"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if is_sse:
                yield f"event: handshake\ndata: {json.dumps(handshake)}\n\n"
            else:
                yield json.dumps(handshake) + "\n"
            
            logger.info(f"Sending handshake: {json.dumps(handshake, indent=2)}")
            
            # Send a test message
            test_message = {
                "type": "test",
                "data": {
                    "message": "Connection established",
                    "protocol": "sse" if is_sse else "http-streamable"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if is_sse:
                yield f"event: message\ndata: {json.dumps(test_message)}\n\n"
            else:
                yield json.dumps(test_message) + "\n"
                
            logger.info(f"Sending test message: {json.dumps(test_message, indent=2)}")
            
            # Keep the connection alive
            counter = 0
            while True:
                await asyncio.sleep(5)
                counter += 1
                keepalive = {
                    "type": "keepalive",
                    "data": {
                        "counter": counter,
                        "protocol": "sse" if is_sse else "http-streamable"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                if is_sse:
                    yield f"event: keepalive\ndata: {json.dumps(keepalive)}\n\n"
                else:
                    yield json.dumps(keepalive) + "\n"
                    
                logger.debug(f"Sending keepalive: {counter}")
                
        except asyncio.CancelledError:
            logger.info("Client disconnected")
        except Exception as e:
            error_msg = f"Error in stream: {str(e)}"
            logger.error(error_msg)
            error_response = {
                "type": "error", 
                "data": {"error": error_msg},
                "timestamp": datetime.utcnow().isoformat()
            }
            if is_sse:
                yield f"event: error\ndata: {json.dumps(error_response)}\n\n"
            else:
                yield json.dumps(error_response) + "\n"
    
    # Set appropriate headers based on the protocol
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    
    if is_sse:
        headers["Content-Type"] = "text/event-stream"
        media_type = "text/event-stream"
    else:
        headers["Content-Type"] = "application/x-ndjson"
        media_type = "application/x-ndjson"
    
    return StreamingResponse(
        event_generator(),
        media_type=media_type,
        headers=headers
    )

# Legacy SSE endpoint for backward compatibility
@app.get("/sse")
async def sse_endpoint():
    """SSE endpoint for n8n MCP Client Tool."""
    async def event_generator():
        try:
            # Initial handshake that n8n expects
            handshake = {
                "endpoint": "/messages",
                "auth": {"type": "none"},
                "protocol": "sse"
            }
            logger.info("Sending handshake")
            yield f"event: handshake\ndata: {json.dumps(handshake)}\n\n"
            
            # Send a test message
            test_message = {
                "type": "test",
                "message": "SSE connection established",
                "timestamp": str(datetime.utcnow())
            }
            logger.info("Sending test message")
            yield f"event: message\ndata: {json.dumps(test_message)}\n\n"
            
            # Keep the connection alive with periodic messages
            counter = 0
            while True:
                await asyncio.sleep(5)
                counter += 1
                keepalive = {
                    "type": "keepalive",
                    "counter": counter,
                    "timestamp": str(datetime.utcnow())
                }
                logger.debug(f"Sending keepalive {counter}")
                yield f"event: keepalive\ndata: {json.dumps(keepalive)}\n\n"
                
        except asyncio.CancelledError:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
    
    # Response headers
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*"
    }
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers
    )

# Add OPTIONS method for CORS preflight
@app.options("/sse")
async def options_sse():
    return JSONResponse(
        content={"status": "ok"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

if __name__ == "__main__":
    import uvicorn
    import ssl
    import os
    
    # Load environment variables
    load_dotenv()
    
    # SSL configuration for HTTPS
    ssl_keyfile = os.getenv("SSL_KEYFILE")
    ssl_certfile = os.getenv("SSL_CERTFILE")
    
    ssl_context = None
    if ssl_keyfile and ssl_certfile:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(ssl_certfile, ssl_keyfile)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("server.log")
        ]
    )
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        log_level="info"
    )
