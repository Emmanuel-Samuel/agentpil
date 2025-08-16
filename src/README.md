# Running the Application

## Issue Explanation

The error `ImportError: attempted relative import with no known parent package` occurs when trying to run the application directly with:

```bash
python src/app.py
```

This happens because Python doesn't recognize the script as part of a package when run directly, causing relative imports to fail.

## Correct Ways to Run the Application

### 1. For Local Development (Recommended)

Run the application from the project root directory using the module syntax:

```bash
# Navigate to the project root directory (where src/ folder is located)
cd /path/to/agentpil

# Run using Python module syntax
python -m src.app
```

Alternatively, you can run with uvicorn directly:

```bash
# From the project root directory
uvicorn src.app:app --host 0.0.0.0 --port 8000
```

**Important:** After starting the server, access it using:
- http://localhost:8000/health
- http://127.0.0.1:8000/health

**Do NOT use** http://0.0.0.0:8000/health as this will not work in your browser on Windows!

## Testing the Chat Endpoint

The application has a `/chat` endpoint that accepts POST requests. Here are several ways to test it:

### Method 1: Using curl (Command Line)

```bash
curl -X POST "http://localhost:8000/chat" \
     -H "Content-Type: application/json" \
     -d "{\"user_id\": \"test_user_123\", \"message\": \"Hello, this is a test message\"}"
```

### Method 2: Using PowerShell (Windows)

```powershell
$body = @{
    user_id = "test_user_123"
    message = "Hello, this is a test message"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/chat" -Method Post -Body $body -ContentType "application/json"
```

### Method 3: Using Python

Create a test script `test_chat.py`:

```python
import requests
import json

url = "http://localhost:8000/chat"
payload = {
    "user_id": "test_user_123",
    "message": "Hello, this is a test message"
}

response = requests.post(url, json=payload)
print(json.dumps(response.json(), indent=2))
```

### Method 4: Using FastAPI's Interactive Documentation

1. Start the server
2. Navigate to http://localhost:8000/docs
3. Find the `/chat` endpoint
4. Click "Try it out"
5. Enter the request body:
   ```json
   {
     "user_id": "test_user_123",
     "message": "Hello, this is a test message"
   }
   ```
6. Click "Execute"

### Expected Response

The chat endpoint will return a JSON response like:

```json
{
  "response": "Echo: Hello, this is a test message",
  "history": [
    {
      "role": "user",
      "content": "Hello, this is a test message"
    },
    {
      "role": "assistant",
      "content": "Echo: Hello, this is a test message"
    }
  ]
}
```

**Note:** The current implementation is a simple echo bot. It stores chat history in Redis and saves conversations to CosmosDB.

### 2. For Production Deployment

The application is configured to run with gunicorn in Azure App Service:

```bash
# This is how it runs in Azure (from the Bicep configuration)
python3 -m gunicorn src.app:app -k uvicorn.workers.UvicornWorker
```

## Environment Variables

Make sure all required environment variables are set. The application expects:

- `COSMOS_DB_DATABASE_NAME`
- `COSMOS_DB_CONTAINER_NAME`
- `COSMOS_DB_URL`
- `COSMOS_DB_KEY`
- `REDIS_PASSWORD`
- `REDIS_URL`

These are loaded from the `.env` file in the `src/` directory.

## Prerequisites

Make sure you have installed all required dependencies:

```bash
pip install -r src/requirements.txt
```

## Troubleshooting

If you still encounter import errors, ensure that:

1. You're running the command from the project root directory (not from within the src directory)
2. All `__init__.py` files are present (they should be included in the project)
3. All required dependencies are installed
4. Environment variables are properly set