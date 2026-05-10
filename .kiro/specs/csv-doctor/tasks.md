# CSV Doctor — Tasks

- [x] 1. Project Scaffold & Configuration
  - Create `requirements.txt` with pinned versions: flask==3.0.3, openai==1.35.7, pandas==2.2.2, numpy==1.26.4, scikit-learn==1.5.0, python-dotenv==1.0.1
  - Create `.env.example` containing only `OPENAI_API_KEY=`
  - Create `backend/__init__.py` (empty)
  - Create `data/rulebook.json` with ~20 data engineering rules covering: missing values, duplicates, type coercion, date normalization, outlier detection, string normalization
  - Create the full directory structure: `backend/`, `static/css/`, `static/js/`, `templates/`, `data/`, `eval/test_csvs/`
  - _Requirements: R8.1, R8.2, R8.4_

- [x] 2. CSV Profiler (`backend/profiler.py`)
  - Implement `profile_csv(csv_text: str) -> dict` that parses CSV text and returns shape, per-column stats (dtype, null_count, null_pct, unique_count, sample_values), duplicate_rows count, 5-row sample, and a raw_summary string
  - Handle parse errors gracefully (return error dict if CSV is malformed)
  - Truncate very large datasets to first 1000 rows for profiling
  - _Requirements: R2.1, R2.2, R2.3, R2.4, R1.3_
  - _Depends on: 1_

- [x] 3. Local Rulebook / RAG (`backend/rulebook.py`)
  - Implement `load_rulebook(path: str) -> list` that loads `data/rulebook.json`
  - Implement `retrieve_rules(query: str, top_k: int = 5) -> str` using TF-IDF cosine similarity (scikit-learn TfidfVectorizer + cosine_similarity)
  - Format retrieved rules as a numbered list string for injection into the AI prompt
  - _Requirements: R3.4_
  - _Depends on: 1_

- [x] 4. AI Engine (`backend/ai_engine.py`)
  - Implement `analyze_dataset(profile: dict, rules: str) -> dict` that builds a system prompt, injects profile JSON and rulebook rules, calls gpt-4o-mini with response_format json_object, returns parsed JSON with issues list and cleaning_code string
  - Each issue object must have: column, issue_type, description, severity, suggested_fix
  - Implement `chat_followup(profile: dict, history: list, user_message: str) -> str` that maintains conversation history with dataset profile in system context
  - Handle OpenAI API errors (rate limits, invalid key, network errors) with descriptive exceptions
  - _Requirements: R3.1, R3.2, R3.3, R5.1, R5.2_
  - _Depends on: 3_

- [x] 5. Code Runner (`backend/code_runner.py`)
  - Implement `run_cleaning_code(csv_text: str, code: str) -> dict` that writes CSV to temp file, writes a Python script loading CSV as df and running cleaning code saving df_cleaned, executes in subprocess with 10-second timeout
  - Return dict with: success (bool), error (str or None), cleaned_csv (str or None), stdout (str)
  - Clean up temp files after execution
  - Handle subprocess.TimeoutExpired and return descriptive error
  - _Requirements: R4.3, R4.4, R4.5_
  - _Depends on: 1_

- [x] 6. Flask Application (`app.py`)
  - Implement GET / serving templates/index.html
  - Implement POST /api/analyze: accept multipart file upload OR JSON csv_text, call profiler then rulebook then ai_engine, store CSV in session temp dir, return profile + issues + cleaning_code + session_id
  - Implement POST /api/run-code: accept session_id and code, retrieve stored CSV, call code_runner, store cleaned CSV, return success/error/stdout/has_cleaned_csv
  - Implement GET /api/download/<session_id> returning cleaned CSV as file download
  - Implement POST /api/chat: accept session_id + history + message, call ai_engine.chat_followup, return reply
  - Add global error handler returning JSON error for all 4xx/5xx
  - Use Flask sessions with secret key from env to store per-session data in temp directory
  - _Requirements: R6.1, R6.2, R6.3, R4.1, R4.2, R5.3_
  - _Depends on: 2, 4, 5_

- [x] 7. HTML Template (`templates/index.html`)
  - Create single-page layout with three sections: Input, Analysis Results, Code and Chat
  - Input section: file upload drop zone + paste textarea + Analyze button + loading spinner
  - Analysis section: profile stats table + issue cards with severity badges (high/medium/low)
  - Code section: pre/code block for generated code + Run Code button + execution result area + download link
  - Chat section: message thread div + input field + send button
  - Add ARIA labels, roles, and keyboard navigation support
  - Link to static/css/style.css and static/js/app.js
  - _Requirements: R6.1, R6.2, R6.3, R6.4_
  - _Depends on: 6_

- [x] 8. CSS Styles (`static/css/style.css`)
  - CSS variables for color palette (dark navy primary, teal accent, light gray background)
  - Responsive layout working on desktop and tablet
  - File drop zone styles with dashed border and hover highlight
  - Issue card styles with severity color coding (red=high, orange=medium, blue=low)
  - Code block styles with monospace dark background
  - Loading spinner animation
  - Chat bubble styles distinguishing user vs assistant messages
  - Alert/error banner styles with dismiss button
  - _Requirements: R6.1, R6.2, R6.4_
  - _Depends on: 7_

- [x] 9. Frontend JavaScript (`static/js/app.js`)
  - File upload handler: drag-and-drop + file input change reading file as text
  - Paste textarea handler detecting CSV text input
  - Analyze button handler: show spinner, POST to /api/analyze, on success render profile table + issue cards + code block storing session_id, on error show error banner
  - Run Code button handler: show spinner, POST to /api/run-code, on success show green message + enable download, on error show red message with stderr
  - Download link handler calling GET /api/download/<session_id>
  - Chat send handler: append user message, POST to /api/chat, append assistant reply, show loading indicator
  - Make code block contenteditable so users can tweak before running
  - Error banner dismiss button
  - _Requirements: R6.1, R6.2, R5.1_
  - _Depends on: 7, 8_

- [x] 10. Eval Test CSVs (`eval/test_csvs/`)
  - Create customers_dirty.csv: duplicate IDs, missing emails, inconsistent date formats, ages as text, blank names
  - Create orders_dirty.csv: negative quantities, missing product names, dollar-sign prices, duplicate order IDs, invalid dates like 13/40/2024
  - Create employees_dirty.csv: mixed salary formats, missing department, duplicate employee IDs, inconsistent phone formatting
  - Create products_dirty.csv: negative prices, missing category, duplicate SKUs, weight as string with units
  - Create transactions_dirty.csv: future dates, missing amounts, duplicate transaction IDs, currency mixed with numbers
  - Create students_dirty.csv: GPA over 4.0, missing student IDs, inconsistent grade formats, duplicate entries
  - Create inventory_dirty.csv: negative stock counts, missing supplier, inconsistent unit types, duplicate item codes
  - Create sales_dirty.csv: missing region, revenue as text, duplicate sale IDs, wrong date format
  - Create users_dirty.csv: invalid email formats, missing usernames, duplicate user IDs, age outliers like 999
  - Create logs_dirty.csv: malformed timestamps, missing severity levels, duplicate log IDs
  - _Requirements: R7.1_
  - _Depends on: 1_

- [x] 11. Eval Script and Test Cases (`eval/`)
  - Create eval/test_cases.json with 10+ entries each containing: id, csv_file, expected_issues (list of keywords), expected_cleaning_steps (list of keywords), description
  - Implement eval/eval.py that loads test cases, reads each CSV, calls Flask /api/analyze endpoint, scores issue detection by checking expected keywords in response, scores code runnability by executing generated code, computes per-case and overall data_quality_score
  - Print formatted results table and save to eval/results.json
  - Add --verbose flag to show full AI responses per test case
  - _Requirements: R7.1, R7.2_
  - _Depends on: 6, 10_

- [x] 12. README.md
  - App description section explaining what it does and who it is for
  - Prerequisites section listing Python 3.11+ and pip
  - Step-by-step setup: clone, create virtualenv, pip install -r requirements.txt, copy .env.example to .env, add OPENAI_API_KEY
  - Run instructions: python app.py then open http://localhost:5000
  - Eval instructions: python eval/eval.py
  - Example invocations describing what to expect
  - Project structure overview
  - _Requirements: R8.3_
  - _Depends on: 6, 11_

- [x] 13. REPORT.md
  - Section 1 What and Why (~200-250 words): what the app does, who it is for, what is hard about getting AI behavior right
  - Section 2 Iterations with 3 versions V1/V2/V3 (~75-150 words each), each containing Change, Motivating example, Delta (metric before to after), Conclusion
  - Section 3 Code Walkthrough (200-300 words): trace one user action through code with file:line references, one design decision, one rejected alternative
  - Section 4 Conclusion: summary of what was learned and what would be tried next
  - _Requirements: R7.3_
  - _Depends on: 11_
