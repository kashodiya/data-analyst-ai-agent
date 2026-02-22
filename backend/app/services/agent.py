"""Main agent service for processing questions and coordinating tools."""

import json
import time
import re
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

from ..models.session import Message, ToolCall
from ..models.responses import StreamChunk
from .llm_client import LLMClient
from .sql_tool import SQLTool

logger = logging.getLogger(__name__)


class Agent:
    """Main agent for processing questions and coordinating tools."""

    def __init__(self, llm_client: LLMClient, sql_tool: SQLTool):
        """Initialize the agent."""
        self.llm_client = llm_client
        self.sql_tool = sql_tool
        self.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        return """You are a helpful data analytics assistant with access to a SQL database.

Your role is to:
1. Answer questions about data by writing and executing SQL queries using the sql_query tool
2. Explain your approach and reasoning
3. Provide clear explanations of SQL queries in plain language
4. Present results in a clear, understandable format

IMPORTANT: You MUST use the sql_query tool function to execute queries. Do not just describe what query you would run - actually execute it using the tool.

When answering questions:
- First, understand what the user is asking for
- If needed, use the get_database_schema tool to examine the database structure
- Use the sql_query tool to execute appropriate SQL queries
- Explain what each query does in simple terms
- Present the results clearly in your response

Always be transparent about:
- What tools you're using and why
- What each SQL query does
- Any limitations or assumptions in your analysis

Remember: Always USE the tools available to you, don't just describe what you would do."""

    async def process_message(
        self,
        message: str,
        session_messages: List[Message],
        include_approach: bool = True,
        include_sql_explanation: bool = True
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Process a user message and stream the response.

        Yields StreamChunk objects with different types:
        - 'text': Regular response text
        - 'tool_call': Information about tool usage
        - 'approach': Explanation of the approach
        - 'sql_explanation': Plain language SQL explanation
        - 'done': Indicates completion
        """
        # Add user message to history
        user_message = Message(
            id="temp",
            session_id="temp",
            role="user",
            content=message,
            timestamp=datetime.utcnow()
        )

        messages = session_messages + [user_message]

        # Track tool calls made during this response
        tool_calls_made = []
        current_response = ""
        current_tool_call = None
        is_collecting_tool = False

        try:
            async for chunk in self.llm_client.stream_completion(
                messages=messages,
                system_prompt=self.system_prompt,
                include_tools=True
            ):
                if "choices" not in chunk or not chunk["choices"]:
                    continue

                choice = chunk["choices"][0]
                delta = choice.get("delta", {})

                # Handle regular content
                if "content" in delta and delta["content"]:
                    content = delta["content"]
                    current_response += content

                    yield StreamChunk(
                        type="text",
                        content=content
                    )

                # Handle tool calls
                if "tool_calls" in delta:
                    for tool_call_delta in delta["tool_calls"]:
                        tool_id = tool_call_delta.get("id")

                        if tool_id:
                            # New tool call starting
                            is_collecting_tool = True
                            current_tool_call = {
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": "",
                                    "arguments": ""
                                }
                            }

                        if "function" in tool_call_delta:
                            func_delta = tool_call_delta["function"]

                            if "name" in func_delta:
                                current_tool_call["function"]["name"] = func_delta["name"]

                            if "arguments" in func_delta:
                                current_tool_call["function"]["arguments"] += func_delta["arguments"]

                # Check if we have a complete tool call
                if current_tool_call and choice.get("finish_reason") == "tool_calls":
                    # Execute the tool call
                    tool_result = await self._execute_tool_call(current_tool_call)
                    tool_calls_made.append(tool_result)

                    # Yield tool call information
                    yield StreamChunk(
                        type="tool_call",
                        tool_call=tool_result.model_dump()
                    )

                    # Get follow-up response from LLM with tool results
                    tool_response_message = Message(
                        id="temp",
                        session_id="temp",
                        role="assistant",
                        content=current_response if current_response else "I'll help you with that.",
                        tool_calls=tool_calls_made,
                        timestamp=datetime.utcnow()
                    )

                    messages_with_tool_response = messages + [tool_response_message]

                    # Stream the follow-up response
                    async for follow_up_chunk in self.llm_client.stream_completion(
                        messages=messages_with_tool_response,
                        system_prompt=self.system_prompt,
                        include_tools=False  # Don't allow more tool calls in follow-up
                    ):
                        if "choices" in follow_up_chunk and follow_up_chunk["choices"]:
                            follow_up_delta = follow_up_chunk["choices"][0].get("delta", {})
                            if "content" in follow_up_delta and follow_up_delta["content"]:
                                content = follow_up_delta["content"]
                                current_response += content
                                yield StreamChunk(type="text", content=content)

                    # Reset for potential next tool call
                    current_tool_call = None
                    is_collecting_tool = False

            # Generate approach explanation if requested
            if include_approach and tool_calls_made:
                approach = self._generate_approach_explanation(message, tool_calls_made)
                yield StreamChunk(
                    type="approach",
                    content=approach
                )

            # Generate SQL explanation if requested and SQL was used
            if include_sql_explanation:
                sql_explanations = []
                for tool_call in tool_calls_made:
                    if tool_call.name == "sql_query" and "query" in tool_call.parameters:
                        explanation = self.sql_tool.explain_query(
                            tool_call.parameters["query"],
                            tool_call.response.get("results") if isinstance(tool_call.response, dict) else None
                        )
                        sql_explanations.append(explanation)

                if sql_explanations:
                    yield StreamChunk(
                        type="sql_explanation",
                        content="\n\n".join(sql_explanations)
                    )

            # Generate visualizations if we have suitable data
            visualizations = []
            logger.info(f"Checking {len(tool_calls_made)} tool calls for visualization opportunities")

            for tool_call in tool_calls_made:
                logger.info(f"Tool call: {tool_call.name}, has response: {tool_call.response is not None}")

                if tool_call.name == "sql_query" and isinstance(tool_call.response, dict):
                    results = tool_call.response.get("results")
                    logger.info(f"SQL query results: {len(results) if results else 0} rows")

                    if results and len(results) > 0:
                        query = tool_call.parameters.get("query", "")
                        logger.info(f"Generating visualizations for query: {query[:100]}")
                        viz_configs = self._generate_visualizations(results, query, message)
                        logger.info(f"Generated {len(viz_configs)} visualization(s)")
                        visualizations.extend(viz_configs)

            # Send visualizations
            logger.info(f"Sending {len(visualizations)} total visualizations")
            for viz in visualizations:
                yield StreamChunk(
                    type="visualization",
                    visualization=viz
                )

            # Signal completion
            yield StreamChunk(
                type="done",
                metadata={
                    "tool_calls_count": len(tool_calls_made),
                    "response_length": len(current_response)
                }
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            yield StreamChunk(
                type="error",
                content=f"An error occurred: {str(e)}"
            )

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> ToolCall:
        """Execute a tool call and return the result."""
        function_name = tool_call["function"]["name"]
        logger.info(f"Executing tool: {function_name}")

        try:
            arguments = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            arguments = {}

        logger.info(f"Tool arguments: {arguments}")

        start_time = time.time()
        response = None
        explanation = arguments.get("explanation", "")

        if function_name == "sql_query":
            query = arguments.get("query", "")
            logger.info(f"Executing SQL query: {query[:200]}")
            results, exec_time, error = await self.sql_tool.execute_query(query)

            logger.info(f"SQL execution - Results: {len(results) if results else 0}, Error: {error}")

            if error:
                response = {"error": error}
            else:
                response = {
                    "results": results,
                    "row_count": len(results),
                    "execution_time": exec_time
                }
                logger.info(f"SQL response prepared with {len(results)} results")

        elif function_name == "get_database_schema":
            table_name = arguments.get("table_name")
            schema = await self.sql_tool.get_schema(table_name)
            response = schema
            explanation = f"Getting schema for {'table ' + table_name if table_name else 'entire database'}"

        else:
            response = {"error": f"Unknown tool: {function_name}"}

        execution_time = time.time() - start_time

        return ToolCall(
            name=function_name,
            parameters=arguments,
            response=response,
            execution_time=execution_time,
            explanation=explanation
        )

    def _generate_approach_explanation(self, question: str, tool_calls: List[ToolCall]) -> str:
        """Generate an explanation of the approach taken."""
        explanation_parts = ["Here's how I approached your question:\n"]

        for i, tool_call in enumerate(tool_calls, 1):
            if tool_call.name == "get_database_schema":
                table_name = tool_call.parameters.get("table_name")
                if table_name:
                    explanation_parts.append(
                        f"{i}. Examined the schema of the '{table_name}' table to understand its structure and relationships."
                    )
                else:
                    explanation_parts.append(
                        f"{i}. Analyzed the complete database schema to identify relevant tables and their relationships."
                    )

            elif tool_call.name == "sql_query":
                query = tool_call.parameters.get("query", "")
                query_upper = query.upper()

                # Analyze the query to provide specific insights
                approach_details = []

                # Identify main operations
                if "JOIN" in query_upper:
                    join_count = query_upper.count("JOIN")
                    if join_count == 1:
                        approach_details.append("Combined data from multiple tables using a JOIN operation")
                    else:
                        approach_details.append(f"Combined data from {join_count + 1} tables using multiple JOIN operations")

                if "GROUP BY" in query_upper:
                    approach_details.append("Grouped the data to perform aggregations")

                if "COUNT(" in query_upper or "SUM(" in query_upper or "AVG(" in query_upper or "MAX(" in query_upper or "MIN(" in query_upper:
                    agg_functions = []
                    if "COUNT(" in query_upper:
                        agg_functions.append("counting")
                    if "SUM(" in query_upper:
                        agg_functions.append("summing")
                    if "AVG(" in query_upper:
                        agg_functions.append("averaging")
                    if "MAX(" in query_upper or "MIN(" in query_upper:
                        agg_functions.append("finding extremes")
                    approach_details.append(f"Performed calculations: {', '.join(agg_functions)}")

                if "WHERE" in query_upper:
                    approach_details.append("Applied filters to focus on specific data")

                if "HAVING" in query_upper:
                    approach_details.append("Filtered aggregated results based on conditions")

                if "ORDER BY" in query_upper:
                    if "DESC" in query_upper:
                        approach_details.append("Sorted results in descending order for better visibility")
                    else:
                        approach_details.append("Sorted results for better readability")

                if "CASE" in query_upper:
                    approach_details.append("Used conditional logic to categorize or transform data")

                if "WINDOW" in query_upper or "OVER (" in query_upper or "OVER(" in query_upper:
                    approach_details.append("Applied window functions for advanced analytics")

                if "SUBQUERY" in query_upper or query_upper.count("SELECT") > 1:
                    approach_details.append("Used subqueries for complex data analysis")

                if "LIMIT" in query_upper:
                    import re
                    limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
                    if limit_match:
                        limit_value = limit_match.group(1)
                        approach_details.append(f"Limited results to top {limit_value} entries")

                # Build the explanation
                if approach_details:
                    explanation_parts.append(
                        f"{i}. Constructed a SQL query to answer your question:"
                    )
                    for detail in approach_details:
                        explanation_parts.append(f"   • {detail}")
                else:
                    explanation_parts.append(
                        f"{i}. Executed a SQL query to retrieve the requested data."
                    )

                # Add custom explanation if provided
                if tool_call.explanation:
                    explanation_parts.append(f"   • Specific goal: {tool_call.explanation}")

        # Add result summary if available
        if tool_calls:
            last_call = tool_calls[-1]
            if last_call.name == "sql_query" and isinstance(last_call.response, dict):
                if "row_count" in last_call.response:
                    row_count = last_call.response["row_count"]
                    if row_count == 0:
                        explanation_parts.append("\nNo matching records were found.")
                    elif row_count == 1:
                        explanation_parts.append("\nFound 1 matching record.")
                    else:
                        explanation_parts.append(f"\nSuccessfully retrieved {row_count} records.")

        return "\n".join(explanation_parts)

    def _generate_visualizations(self, results: List[Dict[str, Any]], query: str, question: str) -> List[Dict[str, Any]]:
        """Generate appropriate visualizations based on the query results."""
        if not results or len(results) == 0:
            return []

        visualizations = []
        columns = list(results[0].keys())
        query_upper = query.upper()

        # Detect the type of data and appropriate visualizations
        # Check if it's time-series data
        has_date = any('date' in col.lower() or 'month' in col.lower() or 'year' in col.lower() for col in columns)
        has_numeric = any(isinstance(results[0][col], (int, float)) for col in columns if results[0][col] is not None)

        # Revenue/Sales over time - Line Chart
        if has_date and has_numeric and ('revenue' in question.lower() or 'sales' in question.lower() or 'trend' in question.lower()):
            date_col = next((col for col in columns if 'date' in col.lower() or 'month' in col.lower()), None)
            value_col = next((col for col in columns if 'revenue' in col.lower() or 'total' in col.lower() or 'sum' in col.lower() or 'amount' in col.lower()), None)

            if date_col and value_col:
                viz = {
                    "type": "line",
                    "title": "Trend Analysis",
                    "description": "This line chart shows the trend over time. The x-axis represents the time period, and the y-axis shows the values. Look for patterns, peaks, and valleys in the data.",
                    "data": {
                        "labels": [str(row[date_col]) for row in results],
                        "datasets": [{
                            "label": value_col.replace('_', ' ').title(),
                            "data": [row[value_col] for row in results],
                            "borderColor": "rgb(75, 192, 192)",
                            "backgroundColor": "rgba(75, 192, 192, 0.2)",
                            "tension": 0.1
                        }]
                    },
                    "options": {
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": f"{value_col.replace('_', ' ').title()} Over Time"
                            }
                        }
                    }
                }
                visualizations.append(viz)

        # Top N items - Bar Chart
        elif len(results) <= 20 and has_numeric and ('top' in question.lower() or 'best' in question.lower() or 'highest' in question.lower()):
            # Find label and value columns
            label_col = next((col for col in columns if 'name' in col.lower() or 'title' in col.lower() or 'country' in col.lower() or 'genre' in col.lower()), columns[0])
            value_col = next((col for col in columns if isinstance(results[0][col], (int, float)) and results[0][col] is not None), None)

            if value_col:
                viz = {
                    "type": "bar",
                    "title": "Ranking Comparison",
                    "description": "This bar chart compares values across different categories. Higher bars indicate larger values. The chart is useful for identifying leaders and comparing relative performance.",
                    "data": {
                        "labels": [str(row[label_col])[:30] for row in results],  # Truncate long labels
                        "datasets": [{
                            "label": value_col.replace('_', ' ').title(),
                            "data": [row[value_col] for row in results],
                            "backgroundColor": [
                                'rgba(255, 99, 132, 0.6)',
                                'rgba(54, 162, 235, 0.6)',
                                'rgba(255, 206, 86, 0.6)',
                                'rgba(75, 192, 192, 0.6)',
                                'rgba(153, 102, 255, 0.6)',
                            ] * 5  # Repeat colors
                        }]
                    },
                    "options": {
                        "indexAxis": "y" if len(results) > 8 else "x",  # Horizontal bars for many items
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": f"Top {len(results)} by {value_col.replace('_', ' ').title()}"
                            }
                        }
                    }
                }
                visualizations.append(viz)

        # Distribution/Segmentation - Pie Chart
        elif len(results) <= 10 and has_numeric and ('distribution' in question.lower() or 'breakdown' in question.lower() or 'percentage' in question.lower() or 'segment' in question.lower()):
            label_col = columns[0] if not isinstance(results[0][columns[0]], (int, float)) else columns[1]
            value_col = next((col for col in columns if isinstance(results[0][col], (int, float)) and results[0][col] is not None), None)

            if value_col:
                viz = {
                    "type": "pie",
                    "title": "Distribution Analysis",
                    "description": "This pie chart shows the proportional distribution of values. Each slice represents a category's share of the total. Larger slices indicate greater contribution to the whole.",
                    "data": {
                        "labels": [str(row[label_col]) for row in results],
                        "datasets": [{
                            "data": [row[value_col] for row in results],
                            "backgroundColor": [
                                'rgba(255, 99, 132, 0.6)',
                                'rgba(54, 162, 235, 0.6)',
                                'rgba(255, 206, 86, 0.6)',
                                'rgba(75, 192, 192, 0.6)',
                                'rgba(153, 102, 255, 0.6)',
                                'rgba(255, 159, 64, 0.6)',
                                'rgba(199, 199, 199, 0.6)',
                                'rgba(83, 102, 255, 0.6)',
                                'rgba(255, 99, 255, 0.6)',
                                'rgba(99, 255, 132, 0.6)',
                            ]
                        }]
                    },
                    "options": {
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": f"Distribution by {label_col.replace('_', ' ').title()}"
                            }
                        }
                    }
                }
                visualizations.append(viz)

        # Comparison of multiple metrics - Radar Chart
        elif len(columns) >= 3 and len(results) <= 5 and all(isinstance(results[0][col], (int, float)) or results[0][col] is None for col in columns[1:]):
            viz = {
                "type": "radar",
                "title": "Multi-Metric Comparison",
                "description": "This radar chart compares multiple metrics across different entities. Each axis represents a different metric. The shape and area help identify strengths and weaknesses.",
                "data": {
                    "labels": [col.replace('_', ' ').title() for col in columns[1:]],
                    "datasets": [{
                        "label": str(row[columns[0]]),
                        "data": [row[col] if row[col] is not None else 0 for col in columns[1:]],
                        "borderColor": f'rgba({50 + i * 50}, {100 + i * 30}, {150 - i * 30}, 1)',
                        "backgroundColor": f'rgba({50 + i * 50}, {100 + i * 30}, {150 - i * 30}, 0.2)'
                    } for i, row in enumerate(results)]
                },
                "options": {
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Comparative Analysis"
                        }
                    }
                }
            }
            visualizations.append(viz)

        # Scatter plot for correlation analysis
        elif len(columns) >= 2 and len(results) >= 5 and all(isinstance(results[0][col], (int, float)) or results[0][col] is None for col in columns[:2]):
            if 'correlation' in question.lower() or 'relationship' in question.lower():
                viz = {
                    "type": "scatter",
                    "title": "Correlation Analysis",
                    "description": "This scatter plot shows the relationship between two variables. Look for patterns: upward trends suggest positive correlation, downward trends suggest negative correlation.",
                    "data": {
                        "datasets": [{
                            "label": "Data Points",
                            "data": [{"x": row[columns[0]], "y": row[columns[1]]} for row in results if row[columns[0]] is not None and row[columns[1]] is not None],
                            "backgroundColor": "rgba(75, 192, 192, 0.6)"
                        }]
                    },
                    "options": {
                        "scales": {
                            "x": {
                                "title": {
                                    "display": True,
                                    "text": columns[0].replace('_', ' ').title()
                                }
                            },
                            "y": {
                                "title": {
                                    "display": True,
                                    "text": columns[1].replace('_', ' ').title()
                                }
                            }
                        },
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": f"{columns[0]} vs {columns[1]}"
                            }
                        }
                    }
                }
                visualizations.append(viz)

        # Default to bar chart for generic numeric data
        elif has_numeric and len(results) <= 25:
            label_col = next((col for col in columns if not isinstance(results[0][col], (int, float))), columns[0])
            value_cols = [col for col in columns if col != label_col and isinstance(results[0][col], (int, float)) and results[0][col] is not None]

            if value_cols:
                datasets = []
                colors = ['rgba(75, 192, 192, 0.6)', 'rgba(255, 99, 132, 0.6)', 'rgba(54, 162, 235, 0.6)', 'rgba(255, 206, 86, 0.6)']

                for i, value_col in enumerate(value_cols[:4]):  # Limit to 4 metrics
                    datasets.append({
                        "label": value_col.replace('_', ' ').title(),
                        "data": [row[value_col] for row in results],
                        "backgroundColor": colors[i % len(colors)]
                    })

                viz = {
                    "type": "bar",
                    "title": "Data Comparison",
                    "description": "This bar chart compares values across categories. Use it to identify patterns, outliers, and relative differences between items.",
                    "data": {
                        "labels": [str(row[label_col])[:30] for row in results],
                        "datasets": datasets
                    },
                    "options": {
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": "Comparative Analysis"
                            }
                        }
                    }
                }
                visualizations.append(viz)

        return visualizations