# Google Calendar MCP Server

A Model-Context-Protocol (MCP) server for Google Calendar integration, built with FastAPI and FastMCP. This server provides tools to interact with Google Calendar and can be used with n8n's MCP Client Tool.

## Features

- List upcoming events from Google Calendar
- Create new calendar events
- Update existing events
- Delete events
- Secure API with Bearer token authentication
- Ready for n8n MCP Client Tool integration

## Prerequisites

- Python 3.8+
- Google Cloud Project with Calendar API enabled
- OAuth 2.0 Client ID credentials from Google Cloud Console

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd calendar_mcp
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Google OAuth 2.0**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Calendar API
   - Create OAuth 2.0 Client ID credentials
   - Download the credentials and save as `client_secret.json` in the project root

5. **Initialize OAuth flow**
   ```bash
   python -m app.auth --init
   ```
   This will open a browser window for authentication. After authenticating, a `token.json` file will be created.

6. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file with your configuration.

## Running the Server

```bash
uvicorn main:app --reload
```

The server will be available at `http://localhost:8000`

## API Endpoints

- `GET /healthz` - Health check endpoint
- `GET /calendar/events` - List upcoming events
- `POST /calendar/events` - Create a new event
- `PATCH /calendar/events/{event_id}` - Update an existing event
- `DELETE /calendar/events/{event_id}` - Delete an event
- `POST /messages` - JSON-RPC endpoint
- `GET /sse` - SSE endpoint for n8n MCP Client Tool

## n8n Integration

1. Add an **MCP Client Tool** node to your n8n workflow
2. Configure the node:
   - **SSE Endpoint**: `http://localhost:8000/sse` (or your server URL)
   - **Auth Type**: None
3. Select the tools you want to expose to the agent

## Available Tools

- `list_events` - List upcoming events
- `create_event` - Create a new calendar event
- `update_event` - Update an existing event
- `delete_event` - Delete an event

## Security

- All sensitive information is stored in the `.env` file (which is gitignored)
- OAuth tokens are stored securely with restricted file permissions
- The refresh token is used to obtain new access tokens as needed

**Note**: This implementation does not include API key authentication. For production use, consider adding appropriate security measures such as:
- Network-level security (VPN, IP whitelisting)
- API Gateway with authentication
- Rate limiting
- HTTPS with proper certificates

## License

MIT
