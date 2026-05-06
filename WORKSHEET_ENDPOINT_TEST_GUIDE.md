# Worksheet Generation Endpoint Test Guide

## Overview

This guide explains how to test the worksheet generation endpoint (`POST /api/v1/worksheets/generate`) to verify it can successfully generate worksheets using RAG (Retrieval-Augmented Generation).

## Prerequisites

1. **Backend Server Running**
   - The FastAPI backend must be running on `http://127.0.0.1:8000`
   - Start with: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

2. **Published Documents**
   - At least one content pack must exist
   - The pack must have documents with status `PUBLISHED`
   - Documents must have embeddings stored (`embedding_v` column)

3. **OpenAI API Configuration**
   - The worksheet service uses `OpenAIEmbeddingProvider` for query embeddings
   - The service uses OpenAI LLM (`gpt-4o-mini`) for worksheet generation
   - Ensure `OPENAI_API_KEY` is set in environment variables or `.env` file

4. **Authentication**
   - A valid user account must exist
   - Test credentials: `test1@gmail.com` / `123456789aA!` or `admin@1ne.ai` / `Admin123!@#`

## Test Script

A test script is available at: `tools/test_worksheet_endpoint.py`

### Usage

```bash
python tools/test_worksheet_endpoint.py
```

### What It Tests

1. **Backend Availability**
   - Checks if server is running on port 8000
   - Provides instructions if not running

2. **Authentication**
   - Attempts login with test credentials
   - Retrieves JWT token

3. **Content Pack Discovery**
   - Finds a content pack with published documents
   - Verifies documents have embeddings

4. **Worksheet Generation**
   - Sends POST request to `/api/v1/worksheets/generate`
   - Request includes:
     - `pack_id`: UUID of content pack
     - `topic_text`: "Introduction to fractions and basic math"
     - `grade`: "6"
     - `subject`: "Mathematics"
     - `num_questions`: 3
     - `difficulty_mix`: {"easy": 0.4, "medium": 0.4, "hard": 0.2}
     - `question_types`: ["mcq", "short_answer"]

5. **Response Validation**
   - Checks for HTTP 200 status
   - Validates response structure:
     - `id`: Worksheet UUID
     - `questions`: List of question objects
     - `answer_key`: Dictionary of answers
     - `marking_scheme`: Dictionary of marking criteria
     - `citations`: List of source chunks used

## Expected Behavior

### Success (HTTP 200)

The endpoint should:
1. **Retrieve Content**: Use vector similarity search to find relevant chunks from published documents
2. **Generate Questions**: Use OpenAI LLM to create questions based on retrieved content
3. **Return Worksheet**: Return a complete worksheet JSON with:
   - Questions with proper structure
   - Answer keys
   - Marking schemes
   - Citations to source chunks

### Sample Request

```json
{
  "pack_id": "7219fec4-7184-4139-8cd0-f05e1e2614ed",
  "topic_text": "Introduction to fractions and basic math",
  "grade": "6",
  "subject": "Mathematics",
  "num_questions": 3,
  "difficulty_mix": {
    "easy": 0.4,
    "medium": 0.4,
    "hard": 0.2
  },
  "question_types": ["mcq", "short_answer"]
}
```

### Sample Response

```json
{
  "id": "uuid-here",
  "pack_id": "7219fec4-7184-4139-8cd0-f05e1e2614ed",
  "topic_text": "Introduction to fractions and basic math",
  "grade": "6",
  "subject": "Mathematics",
  "questions": [
    {
      "id": "q1",
      "type": "mcq",
      "question": "What is 1/2 + 1/4?",
      "options": ["3/4", "2/6", "1/3", "2/4"],
      "correct_answer": "3/4",
      "explanation": "To add fractions, find common denominator...",
      "points": 1,
      "difficulty": "easy",
      "math_content": true
    }
  ],
  "answer_key": {"q1": "3/4"},
  "marking_scheme": {
    "q1": {
      "points": 1,
      "criteria": "Correct answer"
    }
  },
  "citations": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "page_range": "1-2"
    }
  ],
  "created_at": "2026-01-28T12:00:00Z"
}
```

## Common Issues

### 1. Backend Not Running

**Error**: Connection refused or timeout

**Solution**:
```bash
# Start backend server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. No Published Documents

**Error**: HTTP 400 or 404 - "No content found"

**Solution**:
- Ensure documents are ingested and published
- Run E2E ingestion test first: `python tools/run_free_mode_e2e.py`
- Verify documents have `status = 'published'` in database

### 3. OpenAI API Key Missing

**Error**: HTTP 500 - "OpenAI API key not configured"

**Solution**:
- Set `OPENAI_API_KEY` in `.env` file or environment variables
- Restart backend server after setting

### 4. Authentication Failed

**Error**: HTTP 401 - Unauthorized

**Solution**:
- Verify test user exists in database
- Check credentials: `test1@gmail.com` / `123456789aA!`
- Or create a new user account

### 5. No Embeddings Found

**Error**: HTTP 400 - "No content found for pack"

**Solution**:
- Ensure documents have `embedding_v IS NOT NULL`
- Verify embeddings were generated during ingestion
- Check that `embedding_model = 'fake'` or appropriate model name

### 6. LLM Generation Timeout

**Error**: Request timeout (90+ seconds)

**Solution**:
- Check OpenAI API status
- Verify network connectivity
- Increase timeout in test script if needed
- Check backend logs for LLM errors

## Manual Testing

If you prefer to test manually:

### Using curl

```bash
# 1. Login
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test1@gmail.com", "password": "123456789aA!"}'

# 2. Generate worksheet (replace TOKEN and PACK_ID)
curl -X POST http://127.0.0.1:8000/api/v1/worksheets/generate \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "PACK_ID",
    "topic_text": "Introduction to fractions",
    "grade": "6",
    "subject": "Mathematics",
    "num_questions": 3,
    "difficulty_mix": {"easy": 0.4, "medium": 0.4, "hard": 0.2},
    "question_types": ["mcq", "short_answer"]
  }'
```

### Using Python requests

```python
import requests

BASE = "http://127.0.0.1:8000"

# Login
login = requests.post(
    f"{BASE}/api/v1/auth/login",
    json={"email": "test1@gmail.com", "password": "123456789aA!"}
)
token = login.json()["access_token"]

# Generate worksheet
response = requests.post(
    f"{BASE}/api/v1/worksheets/generate",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "pack_id": "YOUR_PACK_ID",
        "topic_text": "Introduction to fractions",
        "grade": "6",
        "subject": "Mathematics",
        "num_questions": 3,
        "difficulty_mix": {"easy": 0.4, "medium": 0.4, "hard": 0.2},
        "question_types": ["mcq", "short_answer"]
    },
    timeout=90
)

print(response.status_code)
print(response.json())
```

## Endpoint Details

### Route

`POST /api/v1/worksheets/generate`

### Authentication

Requires: Bearer token (JWT)

### Request Schema

```python
{
    "pack_id": UUID (required),
    "topic_id": str (optional),
    "topic_text": str (optional, alternative to topic_id),
    "grade": str (optional),
    "subject": str (optional),
    "difficulty_mix": Dict[str, float] (optional, default: {"easy": 0.3, "medium": 0.5, "hard": 0.2}),
    "num_questions": int (required, 1-50),
    "question_types": List[str] (optional, default: ["mcq", "short_answer"])
}
```

### Response Schema

```python
{
    "id": UUID,
    "pack_id": UUID,
    "topic_id": str | None,
    "topic_text": str | None,
    "grade": str | None,
    "subject": str | None,
    "questions": List[WorksheetQuestion],
    "answer_key": Dict[str, str],
    "marking_scheme": Dict[str, Dict],
    "citations": List[Dict] | None,
    "created_at": datetime
}
```

## Implementation Notes

### Worksheet Service Flow

1. **Cache Check**: Checks for existing worksheet with same signature hash
2. **Query Embedding**: Generates embedding for `topic_text` using OpenAI
3. **Vector Retrieval**: Searches for top-k similar chunks using pgvector
4. **Context Building**: Combines retrieved chunks into context string
5. **LLM Generation**: Sends context to OpenAI LLM with worksheet generation prompt
6. **JSON Parsing**: Extracts and validates JSON from LLM response
7. **Cache Storage**: Saves worksheet to database for future reuse
8. **Response**: Returns worksheet JSON with questions, answers, and citations

### Dependencies

- **OpenAI API**: Required for embeddings and LLM generation
- **pgvector**: Required for vector similarity search
- **Published Documents**: Must have embeddings stored
- **Database**: PostgreSQL with pgvector extension

## Next Steps

After successful test:

1. **Verify Questions**: Check that questions are relevant to the topic
2. **Check Citations**: Verify citations point to correct source chunks
3. **Test Different Topics**: Try various topics and subjects
4. **Test Caching**: Generate same worksheet twice to verify caching works
5. **Test Error Cases**: Try invalid pack_id, missing content, etc.

## Summary

The worksheet generation endpoint is ready to test. Ensure:
- ✅ Backend server is running
- ✅ Published documents exist with embeddings
- ✅ OpenAI API key is configured
- ✅ Test user account exists

Then run: `python tools/test_worksheet_endpoint.py`
