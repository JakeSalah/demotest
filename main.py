import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastmcp import FastMCP
from fastmcp.tools import tool
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Google Calendar MCP Server",
    description="MCP server for Google Calendar integration",
    version="1.0.0"
)

# CORS middleware with HTTP Streamable support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# No authentication required

# Import and include routers
from app import calendar_tools, auth
app.include_router(calendar_tools.router)

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

# MCP endpoints
@app.post("/messages")
async def handle_messages(request: Request):
    """Handle JSON-RPC messages."""
    data = await request.json()
    return await mcp.dispatch(data)

# HTTP Streamable endpoint for n8n MCP Client Tool
@app.post("/stream")
async def stream_endpoint():
    """HTTP Streamable endpoint for n8n MCP Client Tool.
    
    This endpoint implements the HTTP Streamable protocol for MCP.
    """
    async def event_generator():
        try:
            # Initial handshake
            handshake = {
                "type": "handshake",
                "data": {
                    "endpoint": "/messages",
                    "auth": {"type": "none"},
                    "protocol": "http-streamable"
                }
            }
            logger.info(f"Sending handshake: {handshake}")
            yield json.dumps(handshake) + "\n"
            
            # Send a test message
            test_message = {
                "type": "test",
                "data": {
                    "message": "Connection established",
                    "timestamp": str(datetime.utcnow())
                }
            }
            logger.info(f"Sending test message: {test_message}")
            yield json.dumps(test_message) + "\n"
            
            # Keep the connection alive
            counter = 0
            while True:
                await asyncio.sleep(5)
                counter += 1
                keepalive = {
                    "type": "keepalive",
                    "data": {
                        "counter": counter,
                        "timestamp": str(datetime.utcnow())
                    }
                }
                logger.debug(f"Sending keepalive: {counter}")
                yield json.dumps(keepalive) + "\n"
                
        except asyncio.CancelledError:
            logger.info("Client disconnected")
        except Exception as e:
            error_msg = f"Error in stream: {str(e)}"
            logger.error(error_msg)
            yield json.dumps({"type": "error", "data": {"error": error_msg}}) + "\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
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
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("mcp_server.log")
        ]
    )
    
    # SSL context for HTTPS
    ssl_keyfile = "certs/key.pem"
    ssl_certfile = "certs/cert.pem"
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(ssl_certfile, ssl_keyfile)
    
    # Start the server with HTTPS
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8002)),
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        log_level="info",
        reload=True
    )
