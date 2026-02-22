# Troubleshooting Charts & Visualizations

## Current Status

✅ **Database**: Chinook is auto-connected
✅ **Frontend**: Chart.js integrated and ready
✅ **Backend**: Visualization generation implemented
⚠️ **Issue**: LLM may not be executing SQL queries via tools

## Quick Diagnostic Steps

### 1. Check Server Logs
Look at the terminal where the server is running for messages like:
- "Auto-connected to Chinook database"
- "Executing tool: sql_query"
- "SQL execution - Results: X"
- "Generated X visualization(s)"

### 2. Test Simple Query First
Try this exact query: **"How many customers are in the database?"**

This should:
- Execute a simple COUNT query
- Return a number
- Show in logs: "Executing tool: sql_query"

### 3. Test Chart Generation
If the simple query works, try: **"Show me the top 5 customers by total purchases"**

This should:
- Execute SQL with JOINs
- Return tabular data
- Generate a bar chart

## Common Issues & Solutions

### Issue: "No database connection configured"
**Solution**: Database now auto-connects to Chinook. Refresh browser and try again.

### Issue: LLM describes query but doesn't execute
**Symptom**: Response says "I would run this query..." but no actual results
**Solution**: The LLM needs to use tools. Try being more direct:
- "Execute a SQL query to show me..."
- "Run SQL to get..."

### Issue: No "Executing tool" in server logs
**Meaning**: LLM isn't calling the sql_query tool
**Possible causes**:
1. LLM endpoint issue
2. Tool definitions not being passed
3. System prompt not instructing tool use

## What Should Happen (When Working)

1. **You ask**: "Show me top 5 artists by sales"

2. **Server logs show**:
   ```
   Executing tool: sql_query
   SQL query: SELECT Artist.Name, COUNT(*) as Sales...
   SQL execution - Results: 5
   Generated 1 visualization(s)
   Sending 1 total visualizations
   ```

3. **Browser console shows**:
   ```
   Received visualization: {type: "bar", title: "Ranking Comparison"...}
   Rendering 1 chart(s) for message: ...
   ```

4. **UI displays**:
   - Text response with data
   - Bar chart below the text
   - Chart title and description

## Debug Mode

Add this to browser console to see all SSE events:
```javascript
// Override fetch to log SSE events
const originalFetch = window.fetch;
window.fetch = function(...args) {
    console.log('Fetch:', args[0]);
    return originalFetch.apply(this, args);
};
```

## Manual Test via API

Test if the backend works directly:
```bash
curl -X POST http://localhost:8080/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "Test"}'
# Note the session ID

curl -X POST http://localhost:8080/api/sessions/{SESSION_ID}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "How many customers are there?"}'
```

## Current Investigation

The issue appears to be that the LLM (Claude 4.5) is not executing the sql_query tool function. This could be because:

1. **Tool calling not enabled**: The endpoint might not support function calling
2. **Model behavior**: The model might need different prompting
3. **API compatibility**: The OpenAI-compatible endpoint might not fully support tools

## Next Steps

1. **Check server logs** when you ask a question
2. **Share what you see** in the logs when asking "How many customers are there?"
3. **Try the manual API test** to see raw response

This will help identify if the issue is:
- LLM not calling tools
- Tools not executing
- Visualizations not generating
- Frontend not rendering