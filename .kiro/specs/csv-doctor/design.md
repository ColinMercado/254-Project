# CSV Doctor — Design

## Architecture Overview

```
254-Project/
├── app.py                  # Flask application entry point
├── requirements.txt        # Pinned Python dependencies
├── .env.example            # OPENAI_API_KEY=
├── README.md
├── REPORT.md
├── static/
│   ├── css/
│   │   └── style.css       # App styles
│   └── js/
│       └── app.js          # Frontend logic (vanilla JS)
├── templates/
│   └── index.html          # Single-page HTML template
├── backend/
│   ├── __init__.py
│   ├── profiler.py         # CSV profiling with pandas
│   ├── ai_engine.py        # OpenAI API calls (analyze + chat)
│   ├── code_runner.py      # Subprocess sandbox for code execution
│   └── rulebook.py         # Local RAG rulebook (in-memory)
├── data/
│   └── rulebook.json       # Data engineering rules for RAG
└── eval/
    ├── eval.py             # Evaluation script
    ├── test_cases.json     # ≥10 labeled test cases
    └── test_csvs/          # Sample dirty CSV files
        ├── customers_dirty.csv
        ├── orders_dirty.csv
        └── ...
```

## Component Design

### 1. Flask Backend (`app.py`)

Routes:
- `GET /` — serve `index.html`
- `POST /api/analyze` — accept CSV (file or text), return profile + AI analysis
- `POST /api/run-code` — execute generated cleaning code, return result + cleaned CSV
- `POST /api/chat` — follow-up Q&A with conversation context
- `GET /api/download/<session_id>` — download cleaned CSV

### 2. CSV Profiler (`backend/profiler.py`)

Uses pandas to compute:
- Shape (rows, cols)
- Per-column: dtype, null count, null %, unique count, sample values
- Duplicate row count
- 5-row sample (head)

Returns a structured dict that feeds into the AI prompt.

### 3. AI Engine (`backend/ai_engine.py`)

**analyze(profile, rulebook_context) → issues + code**

System prompt instructs the model to act as a data engineering assistant. It receives:
- The dataset profile (JSON)
- Relevant rulebook snippets (RAG)
- Instructions to return structured JSON: `{issues: [...], cleaning_code: "..."}`

Each issue object: `{column, issue_type, description, severity}`

**chat(profile, history, user_message) → assistant_reply**

Maintains conversation context. System prompt includes the dataset profile so the model can answer follow-up questions.

Model: `gpt-4o-mini` (cost-efficient, fast)

### 4. Local Rulebook / RAG (`backend/rulebook.py`, `data/rulebook.json`)

A JSON file with ~20 rules covering:
- Missing value handling strategies
- Duplicate detection and removal
- Type coercion (string → numeric, string → datetime)
- Outlier detection
- String normalization
- Date format standardization

At query time, the top-k most relevant rules are selected using simple TF-IDF cosine similarity (scikit-learn, no external vector DB). This keeps everything local.

### 5. Code Runner (`backend/code_runner.py`)

Executes generated Pandas code in a subprocess with:
- A 10-second timeout
- The uploaded CSV loaded as `df`
- Captures stdout, stderr, and whether a `df_cleaned` variable was produced
- Returns `{success: bool, error: str|null, cleaned_csv: str|null}`

Security: runs in a restricted subprocess; does not use `exec()` in the main process.

### 6. Frontend (`templates/index.html`, `static/js/app.js`)

Single-page app with three panels:
1. **Input panel** — file upload + paste textarea + "Analyze" button
2. **Profile + Issues panel** — dataset stats table, issue cards with severity badges
3. **Code + Chat panel** — syntax-highlighted code block, "Run Code" button, download link, chat input

State machine:
- `idle` → `uploading` → `analyzing` → `ready` → `running_code` / `chatting`

Loading spinners shown during `analyzing`, `running_code`, `chatting`.

Error states displayed inline with dismissible alert banners.

## Data Flow

```
User uploads CSV
    → POST /api/analyze
        → profiler.py: compute profile dict
        → rulebook.py: retrieve top-k relevant rules
        → ai_engine.py: build prompt, call OpenAI, parse JSON response
        → return {profile, issues, cleaning_code}
    → Frontend renders profile table + issue cards + code block

User clicks "Run Code"
    → POST /api/run-code
        → code_runner.py: write CSV to temp file, run code in subprocess
        → return {success, error, cleaned_csv_b64}
    → Frontend shows success/error, enables download

User types follow-up question
    → POST /api/chat
        → ai_engine.py: append to history, call OpenAI
        → return {reply}
    → Frontend appends message to chat thread
```

## Key Design Decisions

### Decision 1: In-memory TF-IDF for RAG instead of FAISS
FAISS requires building an index and storing embeddings, which adds setup complexity and an extra OpenAI embeddings API call. Since the rulebook is small (~20 rules), TF-IDF cosine similarity from scikit-learn is fast, fully local, and requires zero setup. Rejected: FAISS (overkill for 20 docs), ChromaDB (adds a dependency and persistence layer).

### Decision 2: Subprocess sandbox for code execution
Running `exec()` in the main Flask process is dangerous — malicious or buggy code could crash the server or access the filesystem. A subprocess with a timeout isolates execution. Rejected: `exec()` in-process (unsafe), RestrictedPython (complex, incomplete coverage).

### Decision 3: Structured JSON output from AI
Asking the model to return plain text makes parsing fragile. Using `response_format={"type": "json_object"}` with a defined schema ensures the frontend always gets `{issues: [...], cleaning_code: "..."}`. Rejected: regex parsing of free-form text (brittle).

## Eval Design (`eval/`)

`eval.py` loads `test_cases.json`, calls `/api/analyze` for each test CSV, then scores:
- Issue detection: checks if each expected issue keyword appears in the AI response
- Code runnability: executes the generated code and checks for errors

Score per case: `(detected + runnable) / (expected_issues + expected_steps)`
Final score: mean across all test cases.
