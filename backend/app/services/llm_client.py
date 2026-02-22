"""LLM client service for Claude API integration."""

import json
import httpx
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from datetime import datetime
import logging

from ..config import settings
from ..models.session import Message, ToolCall

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible client for Claude API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """Initialize the LLM client."""
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = httpx.Timeout(timeout=120.0, connect=10.0)
        self.max_retries = 3

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert Message objects to API format."""
        api_messages = []

        for message in messages:
            content = message.content

            # Include tool call information in assistant messages
            if message.role == "assistant" and message.tool_calls:
                tool_info = "\n\n**Tools Used:**\n"
                for tool_call in message.tool_calls:
                    tool_info += f"- **{tool_call.name}**: {json.dumps(tool_call.parameters)}\n"
                    if tool_call.response:
                        tool_info += f"  Response: {tool_call.response}\n"
                content = content + tool_info

            api_messages.append({
                "role": message.role,
                "content": content
            })

        return api_messages

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "sql_query",
                    "description": "Execute a SQL query on the connected database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The SQL query to execute"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Brief explanation of what this query does"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_database_schema",
                    "description": "Get the schema of the connected database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Optional specific table name to get schema for"
                            }
                        }
                    }
                }
            }
        ]

    async def stream_completion(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        include_tools: bool = True,
        temperature: float = 0.7
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream completion from the LLM."""
        api_messages = self._prepare_messages(messages)

        # Add system message if provided
        if system_prompt:
            api_messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })

        request_body = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": 4096
        }

        if include_tools:
            request_body["tools"] = self._get_tools()
            request_body["tool_choice"] = "auto"

        retry_count = 0
        last_error = None

        while retry_count < self.max_retries:
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=False  # For self-signed certificates
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._get_headers(),
                        json=request_body
                    ) as response:
                        response.raise_for_status()

                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break

                                try:
                                    data = json.loads(data_str)
                                    yield data
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse SSE data: {data_str}")
                                    continue

                return  # Success, exit the retry loop

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(f"HTTP error in LLM request: {e}")
                if e.response.status_code == 429:  # Rate limit
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                else:
                    raise

            except Exception as e:
                last_error = e
                logger.error(f"Error in LLM request: {e}")
                retry_count += 1
                await asyncio.sleep(2 ** retry_count)

        # All retries exhausted
        raise Exception(f"Failed after {self.max_retries} retries. Last error: {last_error}")

    async def complete(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        include_tools: bool = True,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Get a non-streaming completion from the LLM."""
        api_messages = self._prepare_messages(messages)

        if system_prompt:
            api_messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })

        request_body = {
            "model": self.model,
            "messages": api_messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": 4096
        }

        if include_tools:
            request_body["tools"] = self._get_tools()
            request_body["tool_choice"] = "auto"

        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=request_body
            )
            response.raise_for_status()
            return response.json()