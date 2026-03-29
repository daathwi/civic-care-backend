import json
import logging
import httpx
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

async def get_dynamic_schema(db: AsyncSession) -> str:
    """Fetch all tables and columns dynamically from PostgreSQL public schema."""
    query = """
    SELECT table_name, string_agg(column_name || ' (' || data_type || ')', ', ') as columns
    FROM information_schema.columns
    WHERE table_schema = 'public'
    GROUP BY table_name
    """
    result = await db.execute(text(query))
    rows = result.fetchall()
    
    schema_lines = []
    for row in rows:
        schema_lines.append(f"- {row.table_name} ({row.columns})")
        
    return "\n".join(schema_lines)

async def generate_sql(db: AsyncSession, question: str) -> str:
    schema_context = await get_dynamic_schema(db)
    
    prompt = f"""You are a PostgreSQL expert mapping natural language to SQL for the CivicCare database.
The database has the exact following tables and columns (DYNAMICALLY LOADED):

{schema_context}

CRITICAL DATA HINTS AND JOINS (MUST FOLLOW):
1. `users(id)` is the Primary Key for users.
2. `worker_profiles(user_id)` is a Foreign Key to `users(id)`. To join workers: `FROM users JOIN worker_profiles ON users.id = worker_profiles.user_id`.
3. `grievances(ward_id)` joins to `wards(id)`.
4. `users(ward_id)` joins to `wards(id)`.
5. `grievances(reporter_id)` joins to `users(id)`.
6. Enums: 
   - `users.role` in ('citizen', 'fieldManager', 'fieldAssistant', 'admin')
   - `worker_profiles.current_status` in ('onDuty', 'offDuty')
   - `grievances.status` in ('pending', 'assigned', 'inprogress', 'resolved', 'escalated')
   - `grievances.priority` in ('Low', 'Medium', 'High', 'Critical')

HARD RULES (NON-NEGOTIABLE):
1. **ILIKE vs =**: Use `ILIKE` for case-insensitive string searching (e.g., `WHERE name ILIKE '%user%'`). However, for **Enum** columns (status, priority, role, current_status), use the `=` operator for exact matches (e.g., `WHERE status = 'pending'`). If you must use `ILIKE` on an Enum, you MUST cast it to text: `status::TEXT ILIKE 'pending'`.
2. SEARCH PRECISION: If a user asks for a specific name (e.g., 'South'), match it exactly (e.g., `WHERE name ILIKE 'South'`) first or avoid leading wildcards if it might overlap with other names (e.g., 'Shahadra South'). 
3. **NEGATIONS**: If a user asks for "not X" or "excluding X", use the logical `NOT` operator with Enum-appropriate equality (e.g., `WHERE status != 'escalated'`). NEVER include the word 'not' inside the string literal.
4. ONLY use columns listed in the schema. Do not invent columns.
5. Output EXACTLY a raw SQL SELECT query. Do not add any explanation or preamble.
6. ALWAYS use fully qualified names or explicit aliases in JOINs.
7. If the user asks for the "best" citizen, order by users.cis_score DESC NULLS LAST.

EXAMPLES:
Q: How many escalated grievances?
A: SELECT COUNT(*) FROM grievances WHERE status = 'escalated'
Q: Who is Ravi Shukla?
A: SELECT * FROM users WHERE name ILIKE 'Ravi Shukla'
Q: Grievances that are NOT escalated
A: SELECT * FROM grievances WHERE status != 'escalated'
Q: Wards in South Zone
A: SELECT w.name FROM wards w JOIN zones z ON w.zone_id = z.id WHERE z.name ILIKE 'South'
Q: Find grievances related to 'water'
A: SELECT * FROM grievances WHERE title ILIKE '%water%' OR description ILIKE '%water%'
Q: Officers in South zone
A: SELECT u.name FROM users u JOIN worker_profiles wp ON u.id = wp.user_id JOIN wards w ON u.ward_id = w.id JOIN zones z ON w.zone_id = z.id WHERE z.name ILIKE '%south%' OR z.code ILIKE '%south%'
Q: How many field assistants are on duty?
A: SELECT COUNT(*) FROM users u JOIN worker_profiles wp ON u.id = wp.user_id WHERE u.role = 'fieldAssistant' AND wp.current_status = 'onDuty'
Q: What wards are ruled by BJP?
A: SELECT w.name FROM wards w JOIN political_parties p ON w.party_id = p.id WHERE p.short_code = 'BJP'

User Question: {question}
SQL Query:"""
    
    payload = {
        "model": "qwen2.5-coder",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            sql = data.get("response", "").strip()
            
            # Force extract SQL if the model hallucinates markdown blocks
            import re
            sql_match = re.search(r'```(?:sql)?\n(.*?)```', sql, re.DOTALL | re.IGNORECASE)
            if sql_match:
                sql = sql_match.group(1).strip()
            else:
                # Basic cleanup if no markdown block but backticks exist
                if sql.startswith("```sql"):
                    sql = sql[6:]
                if sql.startswith("```"):
                    sql = sql[3:]
                if sql.endswith("```"):
                    sql = sql[:-3]
            
            return sql.strip()
    except Exception as e:
        logger.error(f"Failed to generate SQL: {e}")
        return "NONE"

async def execute_query(db: AsyncSession, sql: str) -> str:
    if not sql or sql.upper() == "NONE":
        return "No relevant database query was generated."
        
    # Security: extremely basic read-only check
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: Generation produced a non-SELECT query."
        
    try:
        result = await db.execute(text(sql))
        rows = result.fetchall()
        
        if not rows:
            return "No results found."
            
        # Convert rows to a list of dicts for JSON
        keys = result.keys()
        dict_rows = [dict(zip(keys, row)) for row in rows]
        
        # Limit rows to avoid huge context windows for the final summary
        return json.dumps(dict_rows[:50], default=str)
    except Exception as e:
        logger.error(f"Failed to execute AI SQL {sql}: {e}")
        return f"Database error: {str(e)}"

async def ask_database_stream(db: AsyncSession, question: str) -> AsyncGenerator[str, None]:
    """
    Two-step pipeline: generate SQL -> execute -> stream natural language back.
    """
    yield json.dumps({"type": "status", "content": "Analyzing query..."}) + "\n\n"
    sql = await generate_sql(db, question)
    print(f"\n[AI CHATBOT] Generating SQL for: '{question}'\n[AI CHATBOT] Executing SQL: {sql}\n")
    
    if sql != "NONE" and sql.upper().startswith("SELECT"):
        yield json.dumps({"type": "status", "content": f"Running query: {sql}"}) + "\n\n"
        db_result = await execute_query(db, sql)
        final_prompt = (
            f"You are CivicCare Admin Assistant. You must answer the user's question clearly and concisely.\n\n"
            f"User Question: {question}\n"
            f"Database Results (JSON): {db_result}\n\n"
            f"**IMPORTANT DATA GUIDELINES**:\n"
            f"1. If the database results contain one or more records, ALWAYS present them in a clear Markdown table.\n"
            f"2. Use appropriate headers for the columns.\n"
            f"3. NEVER wrap tables in code blocks (triple backticks). Output raw Markdown table syntax directly.\n"
            f"4. Provide a brief summary of what the table shows.\n\n"
            f"Provide your final answer now."
        )
    else:
        yield json.dumps({"type": "status", "content": "Responding..."}) + "\n\n"
        final_prompt = (
            f"You are CivicCare Admin Assistant. An admin has asked you a question, but it doesn't seem to require a database query, or I failed to map it to one.\n\n"
            f"User Question: {question}\n\n"
            f"Please respond to the admin helpfully."
        )
        
    payload = {
        "model": "qwen2.5-coder",
        "prompt": final_prompt,
        "stream": True,
        "options": {
            "temperature": 0.4,
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", 
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                # Escape newlines and quotes for JSON SSE wrapper
                                escaped_token = json.dumps({"type": "token", "content": token})
                                yield f"{escaped_token}\n\n"
                        except json.JSONDecodeError:
                            continue
                            
        # Signal completion
        yield json.dumps({"type": "done"}) + "\n\n"
    except Exception as e:
        logger.error(f"Failed to stream final response: {e}")
        yield json.dumps({"type": "error", "content": f"Failed to connect to AI: {str(e)}"}) + "\n\n"

