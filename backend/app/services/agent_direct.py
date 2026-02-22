"""Direct SQL execution agent that works without function calling."""

import re
import json
import time
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime

from ..models.session import Message, ToolCall
from ..models.responses import StreamChunk
from .llm_client import LLMClient
from .sql_tool import SQLTool

logger = logging.getLogger(__name__)


class DirectAgent:
    """Agent that extracts and executes SQL directly from LLM responses."""

    def __init__(self, llm_client: LLMClient, sql_tool: SQLTool):
        """Initialize the agent."""
        self.llm_client = llm_client
        self.sql_tool = sql_tool

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        return """You are a data analytics assistant with access to a Chinook music store database.

When answering questions about data:
1. Write the SQL query you'll use, enclosed in ```sql``` code blocks
2. I will execute the query and show you the results
3. Then provide your analysis of the results

The database contains these tables:
- Artist (ArtistId, Name)
- Album (AlbumId, Title, ArtistId)
- Track (TrackId, Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
- Customer (CustomerId, FirstName, LastName, Company, Address, City, State, Country, etc.)
- Invoice (InvoiceId, CustomerId, InvoiceDate, Total, etc.)
- InvoiceLine (InvoiceLineId, InvoiceId, TrackId, UnitPrice, Quantity)
- Employee (EmployeeId, FirstName, LastName, Title, ReportsTo, etc.)
- Genre (GenreId, Name)
- MediaType (MediaTypeId, Name)
- Playlist (PlaylistId, Name)
- PlaylistTrack (PlaylistId, TrackId)

IMPORTANT: Always write SQL queries in ```sql``` code blocks so they can be executed."""

    def _extract_sql_queries(self, text: str) -> List[str]:
        """Extract SQL queries from markdown code blocks."""
        sql_pattern = r'```sql\s*(.*?)\s*```'
        matches = re.findall(sql_pattern, text, re.DOTALL | re.IGNORECASE)
        return matches

    async def process_message(
        self,
        message: str,
        session_messages: List[Message],
        include_approach: bool = True,
        include_sql_explanation: bool = True
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process a message and stream the response."""

        # First, get the LLM to write SQL queries
        messages = session_messages + [Message(
            id="temp",
            session_id="temp",
            role="user",
            content=message,
            timestamp=datetime.utcnow()
        )]

        current_response = ""
        sql_queries = []
        query_results = []

        logger.info(f"DirectAgent processing message: {message[:100]}")

        # Get initial response from LLM
        async for chunk in self.llm_client.stream_completion(
            messages=messages,
            system_prompt=self._get_system_prompt(),
            include_tools=False  # Don't use tools
        ):
            if "choices" in chunk and chunk["choices"]:
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta and delta["content"]:
                    content = delta["content"]
                    current_response += content

                    # Stream the content
                    yield StreamChunk(type="text", content=content)

                    # Check for SQL queries
                    new_queries = self._extract_sql_queries(current_response)
                    for query in new_queries:
                        if query not in sql_queries:
                            sql_queries.append(query)
                            logger.info(f"Found SQL query: {query[:100]}")

        # Log the complete response and extracted queries
        logger.info(f"LLM response length: {len(current_response)}")
        logger.info(f"Extracted {len(sql_queries)} SQL queries")
        if not sql_queries and "```" in current_response:
            logger.warning("Response contains ``` but no SQL extracted")
            logger.info(f"Response excerpt: {current_response[:500]}")

        # Execute SQL queries if found
        tool_calls = []
        all_results = []

        for query in sql_queries:
            logger.info(f"Executing extracted SQL: {query[:200]}")

            # Execute the query
            results, exec_time, error = await self.sql_tool.execute_query(query)

            # Create tool call record
            tool_call = ToolCall(
                name="sql_query",
                parameters={"query": query},
                response={"results": results, "error": error} if error else {"results": results, "row_count": len(results)},
                execution_time=exec_time,
                explanation=f"Executed SQL query to answer: {message[:100]}"
            )
            tool_calls.append(tool_call)

            if results:
                all_results.extend(results)
                query_results.append((query, results))

            # Send tool call info
            yield StreamChunk(
                type="tool_call",
                tool_call=tool_call.model_dump()
            )

            # Send results back to user
            if error:
                yield StreamChunk(type="text", content=f"\n\n**Query Error:** {error}\n")
            else:
                yield StreamChunk(type="text", content=f"\n\n**Query returned {len(results)} rows**\n")

                # Show first few results
                if results and len(results) > 0:
                    # Create a simple table representation
                    if len(results) <= 10:
                        headers = list(results[0].keys())
                        yield StreamChunk(type="text", content="\n| " + " | ".join(headers) + " |\n")
                        yield StreamChunk(type="text", content="|" + "|".join(["---"] * len(headers)) + "|\n")

                        for row in results[:10]:
                            row_str = "| " + " | ".join(str(row[h]) for h in headers) + " |\n"
                            yield StreamChunk(type="text", content=row_str)

        # Generate visualizations based on queries and results
        logger.info(f"Query results to visualize: {len(query_results)}")
        if query_results:
            for query, results in query_results:
                logger.info(f"Processing results: {len(results)} rows")
                if results and len(results) > 0:
                    viz_configs = self._generate_visualizations(results, query, message)
                    logger.info(f"Generated {len(viz_configs)} visualizations")
                    for viz in viz_configs:
                        logger.info(f"Sending visualization: {viz['type']}, title: {viz.get('title')}")
                        yield StreamChunk(
                            type="visualization",
                            visualization=viz
                        )

        # Generate approach explanation
        if include_approach and sql_queries:
            approach = f"Here's how I approached your question:\n\n"
            approach += f"1. Analyzed your question about: {message[:100]}\n"
            approach += f"2. Wrote {len(sql_queries)} SQL query/queries to get the data\n"
            approach += f"3. Executed the queries against the Chinook database\n"
            if all_results:
                approach += f"4. Retrieved {len(all_results)} total rows of data\n"
                approach += f"5. Generated visualizations to help understand the results\n"

            yield StreamChunk(type="approach", content=approach)

        # SQL explanation
        if include_sql_explanation and sql_queries:
            explanation = "**SQL Query Explanation:**\n\n"
            for i, query in enumerate(sql_queries, 1):
                explanation += f"Query {i}:\n"
                explanation += self._explain_query(query)
                explanation += "\n\n"

            yield StreamChunk(type="sql_explanation", content=explanation)

        # Done
        yield StreamChunk(
            type="done",
            metadata={"queries_executed": len(sql_queries), "total_results": len(all_results)}
        )

    def _explain_query(self, query: str) -> str:
        """Generate a simple explanation of the SQL query."""
        query_upper = query.upper()
        explanation = []

        if "SELECT" in query_upper:
            explanation.append("• Selecting data from the database")
        if "JOIN" in query_upper:
            explanation.append("• Combining data from multiple tables")
        if "WHERE" in query_upper:
            explanation.append("• Filtering results based on conditions")
        if "GROUP BY" in query_upper:
            explanation.append("• Grouping data for aggregation")
        if "ORDER BY" in query_upper:
            if "DESC" in query_upper:
                explanation.append("• Sorting results in descending order")
            else:
                explanation.append("• Sorting results in ascending order")
        if "LIMIT" in query_upper:
            explanation.append("• Limiting the number of results")

        return "\n".join(explanation) if explanation else "Executing a database query"

    def _generate_visualizations(self, results: List[Dict[str, Any]], query: str, question: str) -> List[Dict[str, Any]]:
        """Generate appropriate visualizations based on the query results."""
        if not results or len(results) == 0:
            return []

        visualizations = []
        columns = list(results[0].keys())

        # Detect numeric columns
        numeric_cols = []
        text_cols = []

        for col in columns:
            if results[0][col] is not None:
                if isinstance(results[0][col], (int, float)):
                    numeric_cols.append(col)
                else:
                    text_cols.append(col)

        # Generate appropriate chart based on data structure
        if len(numeric_cols) > 0 and len(text_cols) > 0 and len(results) <= 20:
            # Bar chart for categorical data with numeric values
            label_col = text_cols[0]
            value_col = numeric_cols[0]

            viz = {
                "type": "bar",
                "title": f"{value_col.replace('_', ' ').title()} by {label_col.replace('_', ' ').title()}",
                "description": "This bar chart shows the data distribution. Higher bars indicate larger values.",
                "data": {
                    "labels": [str(row[label_col])[:30] for row in results],
                    "datasets": [{
                        "label": value_col.replace('_', ' ').title(),
                        "data": [row[value_col] if row[value_col] is not None else 0 for row in results],
                        "backgroundColor": 'rgba(75, 192, 192, 0.6)',
                        "borderColor": 'rgba(75, 192, 192, 1)',
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": f"Analysis: {question[:50]}"
                        }
                    }
                }
            }
            visualizations.append(viz)

            # Add pie chart if it looks like distribution data
            if len(results) <= 10 and any(word in question.lower() for word in ['distribution', 'percentage', 'share', 'proportion']):
                viz_pie = {
                    "type": "pie",
                    "title": f"Distribution of {label_col.replace('_', ' ').title()}",
                    "description": "This pie chart shows the proportional distribution.",
                    "data": {
                        "labels": [str(row[label_col])[:30] for row in results],
                        "datasets": [{
                            "data": [row[value_col] if row[value_col] is not None else 0 for row in results],
                            "backgroundColor": [
                                'rgba(255, 99, 132, 0.6)',
                                'rgba(54, 162, 235, 0.6)',
                                'rgba(255, 206, 86, 0.6)',
                                'rgba(75, 192, 192, 0.6)',
                                'rgba(153, 102, 255, 0.6)',
                                'rgba(255, 159, 64, 0.6)',
                            ] * 2
                        }]
                    }
                }
                visualizations.append(viz_pie)

        return visualizations