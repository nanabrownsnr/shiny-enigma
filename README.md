# Replicate MCP Server

A production-ready MCP server for integrating with Replicate's AI models, built for the Twynity platform. This server allows authenticated Twynity personas to connect their Replicate accounts, discover available models, execute predictions, and access generated outputs.

## Features

- **Replicate Account Integration**: Connect and manage multiple Replicate accounts via API tokens
- **Model Discovery**: Search, list, and retrieve detailed information about available Replicate models
- **Prediction Execution**: Create, monitor, and cancel predictions with both synchronous and asynchronous support
- **MCP Tool Integration**: Full support for MCP tools with proper authentication and authorization
- **MCP App UI**: Web-based interface for interacting with the Replicate service
- **Security**: JWT authentication, persona-aware access control, encrypted credential storage
- **Licensing & Usage Tracking**: License validation and usage reporting integration

## Architecture

The server implements Twynity's platform architecture:
- FastMCP server with MCP transport
- JWT/JWKS verification for authentication 
- Persona-aware request context and authorization
- MongoDB-backed connection management
- License validation and usage reporting
- Health checks and service configuration
- MCP tool discovery and execution mechanisms
- MCP App UI integration

## Requirements

- Python 3.11+
- MongoDB database
- Twynity Account Service access
- Replicate API token

## Getting Started

1. Set up environment variables in `.env` file from `.env.example`
2. Install dependencies: `pip install -e .`
3. Run the server: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Configuration

See `.env.example` for required environment variables including:
- MONGODB_URI - Connection to MongoDB
- ENCRYPTION_KEY - For encrypting stored credentials 
- ACCOUNT_SERVICE_URL - Twynity account service endpoint
- LICENSE_KEY - License validation key

## Docker Deployment

Docker configuration is included. Build with:
```
docker build -t replicate-mcp-server .
docker run -p 8000:8000 replicate-mcp-server
```

## MCP Tools

The following MCP tools are available:
- `search_models`
- `list_models` 
- `get_model_info`
- `get_model_version`
- `create_prediction`
- `get_prediction_status`
- `cancel_prediction`
- `wait_for_prediction`
- `check_replicate_connection`

## License

MIT License