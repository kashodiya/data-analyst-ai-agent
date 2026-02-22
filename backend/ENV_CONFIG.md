# Environment Configuration

## Setup Instructions

1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update the values in `.env` with your actual configuration:
   - `LLM_BASE_URL`: Your LLM API endpoint
   - `LLM_API_KEY`: Your API key for the LLM service
   - `LLM_MODEL`: The model to use (default: claude4.5)
   - `DATABASE_PATH`: Path to the SQLite database
   - `HOST`: Server host (default: 0.0.0.0)
   - `PORT`: Server port (default: 8080)
   - `CORS_ORIGINS`: Allowed CORS origins
   - `LOG_LEVEL`: Logging level (INFO, DEBUG, WARNING, ERROR)

## Security Notes

- **Never commit `.env` files to version control**
- The `.env` file is already added to `.gitignore`
- Keep your API keys and sensitive data secure
- Use different API keys for development and production
- Rotate API keys regularly

## Required Environment Variables

The following variables MUST be set for the application to run:
- `LLM_BASE_URL`
- `LLM_API_KEY`

All other variables have defaults in the application configuration.