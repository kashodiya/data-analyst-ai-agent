# Data Analytics Agent - Demo Script

## Setup (30 seconds)

1. Start the application:
   ```bash
   cd agent2/backend
   uv run uvicorn app.main:app --reload --port 8080
   ```

2. Open browser: `http://localhost:8080`

3. Connect to Chinook database:
   - Click database icon (🗄️)
   - Enter: `../data/chinook.db`
   - Select: `sqlite`
   - Click: Connect

## Demo Flow (5-7 minutes)

### 1. Introduction (30 seconds)
"This is a Data Analytics Agent that lets you ask questions about your data in plain English. It uses AI to understand your questions, generates SQL queries, and explains everything it does."

### 2. Simple Query (1 minute)
**Ask:** "How many customers do we have?"

**Highlights:**
- Natural language understanding
- Instant SQL generation
- Clear result presentation

### 3. Business Intelligence (1 minute)
**Ask:** "Show me the top 5 best-selling artists with their total revenue"

**Highlights:**
- Complex JOIN operations handled automatically
- Approach explanation shows the logic
- SQL explanation in plain language

### 4. Trend Analysis (1 minute)
**Ask:** "What's the monthly revenue trend for 2012?"

**Highlights:**
- Time-series analysis capabilities
- Automatic date handling
- Results formatted as a table

### 5. Advanced Analytics (1.5 minutes)
**Ask:** "Which genre has the highest average track price and how does it compare to the overall average?"

**Highlights:**
- Multiple aggregations in one query
- Comparative analysis
- Tool usage transparency (expandable details)

### 6. Customer Insights (1 minute)
**Ask:** "Segment customers into high, medium, and low value groups based on their lifetime purchases"

**Highlights:**
- Complex business logic implementation
- CASE statements generated automatically
- Actionable insights

### 7. Interactive Follow-up (1 minute)
**Ask:** "Now show me just the high-value customers with their countries"

**Highlights:**
- Context awareness from previous queries
- Quick iterations
- Session persistence

## Key Talking Points

### Transparency
- "Notice how the agent shows its approach - you can see exactly what it's doing"
- "The SQL explanation helps non-technical users understand the logic"
- "Tool usage details are available but collapsible to reduce clutter"

### Intelligence
- "The agent understands context and business terminology"
- "It automatically determines the right tables and relationships"
- "Complex queries that would take minutes to write are generated instantly"

### Flexibility
- "Works with any SQLite database - just point to your file"
- "Handles everything from simple counts to complex analytics"
- "Sessions are saved so you can return to previous conversations"

### Safety
- "Read-only queries ensure data safety"
- "Query timeout protection prevents system overload"
- "Result limits keep responses manageable"

## Quick Wins to Show

1. **Multi-table JOIN**: "List all Iron Maiden tracks with their album names"
2. **Aggregation**: "Average invoice value by country"
3. **Ranking**: "Top 10 longest tracks in the database"
4. **Filtering**: "Customers from USA who spent more than $40"
5. **Grouping**: "Number of tracks per genre"

## Common Questions & Answers

**Q: What databases does it support?**
A: Currently SQLite, with PostgreSQL and MySQL coming soon.

**Q: Can it modify data?**
A: No, it's read-only for safety. Only SELECT queries are allowed.

**Q: What AI model does it use?**
A: Claude 4.5, providing advanced natural language understanding.

**Q: Can it handle complex queries?**
A: Yes, it handles JOINs, subqueries, aggregations, and window functions.

**Q: Is the conversation history saved?**
A: Yes, all sessions are persisted in a local SQLite database.

## Troubleshooting

**If no results appear:**
- Check the browser console for errors
- Ensure the database is connected (green notification)
- Verify the server is running (check terminal)

**If queries fail:**
- The question might be too ambiguous - try rephrasing
- Check if the requested data exists in the database
- Look at the error message for clues

## Impressive Finale

**Ask:** "Give me a complete business intelligence summary: total revenue, customer count, best-selling artist, most popular genre, top customer, and average order value"

This showcases the agent's ability to handle complex, multi-faceted questions and provide comprehensive business insights in seconds.

## Post-Demo

- Show the CHINOOK_GUIDE.md for more example questions
- Mention the extensibility (adding new tools, databases)
- Highlight the open architecture (FastAPI + Vue.js)
- Discuss potential enhancements (visualizations, exports)

---

**Remember:** Let the agent's capabilities speak for themselves. The transparency and explanation features are the key differentiators!