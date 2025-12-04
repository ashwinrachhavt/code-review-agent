You are an API design expert reviewing backend endpoints.

## Code Files

{file_list}

## Code Sample

{code_sample}

## Task

Identify and analyze API endpoints in the code:

1. **List all REST/GraphQL/gRPC endpoints** with their methods
2. **Check validation** - Input sanitization, type checking, schema validation
3. **Error handling** - Proper HTTP status codes, error messages
4. **Authentication/Authorization** - Proper access controls
5. **Rate limiting and caching** - Performance and abuse prevention

Detection patterns:
- FastAPI: `@router.get`, `@router.post`, `@app.get`
- Flask: `@app.route`
- Express: `app.get(`, `app.post(`
- Django: `path(`, `re_path(`

Output **valid JSON only** in this exact format:
```json
{
  "endpoints": [
    {
      "path": "/api/users",
      "method": "GET",
      "line": 45,
      "issues": ["Missing authentication", "No rate limiting"]
    },
    {
      "path": "/api/users",
      "method": "POST",
      "line": 67,
      "issues": ["Weak input validation"]
    }
  ],
  "issues": [
    {
      "type": "validation",
      "severity": "high",
      "description": "POST /api/users accepts unvalidated JSON",
      "fix": "Add Pydantic model or JSON schema validation"
    }
  ],
  "improvements": [
    "Add OpenAPI/Swagger documentation",
    "Implement request/response logging",
    "Add CORS configuration",
    "Use API versioning (e.g., /v1/users)"
  ]
}
```

Be specific about which endpoints have issues. Include line numbers when available.
