# REPORT.md — CSV Doctor

---

## 1. What & Why

CSV Doctor is an AI-powered web application that helps data engineering students diagnose and clean messy CSV datasets. A user uploads or pastes a CSV file, and the app profiles the data, identifies quality issues, explains each problem in plain English, generates runnable Python/Pandas cleaning code, and supports follow-up questions through a chat interface.

The target audience is students like me who are learning data engineering and regularly encounter real-world datasets that are far from clean. Before building a pipeline or running analysis, you need to know what is wrong with the data — but beginners often do not know what to look for or how to fix it. CSV Doctor acts as a knowledgeable assistant that walks through the dataset and explains every problem it finds.

Getting the AI behavior right is genuinely hard for several reasons. First, the model must only report issues that are actually present in the data — hallucinating problems that do not exist is worse than missing a real one, because it erodes trust. Second, the generated Pandas code must actually run without errors on the specific CSV provided, not just look plausible. Third, the explanations must be accurate and beginner-friendly at the same time, which requires the model to calibrate its language to the audience. Finally, different datasets have different dominant issues, so a single rigid prompt tends to miss edge cases like currency-formatted numbers, mixed date formats, or encoding artifacts. These challenges make this problem a good fit for a retrieval-augmented, iterative AI workflow rather than a single extraction call.

---

## 2. Iterations

### V1 — Baseline: Single Prompt, No RAG, No Code Validation

**Change:** The initial version sent the dataset profile directly to GPT-4o-mini with a simple system prompt asking it to list issues and generate cleaning code. No rulebook, no structured output format, no code execution.

**Motivating example:** On `orders_dirty.csv`, the model returned a free-text paragraph that mentioned "some price formatting issues" without specifying the column name or the dollar-sign pattern. The generated code used `df['price'].astype(float)` directly, which crashed because the values contained `$` characters. The eval script could not parse the response reliably because the output format varied between runs.

**Delta:** data_quality_score = 0.38 (baseline). Issue detection was inconsistent — the model sometimes invented issues not present in the data, and the free-text format made keyword matching unreliable. Code runnability was 3/10 (30%) because most generated code assumed clean numeric types.

**Conclusion:** The free-text output format was the biggest problem. Without a schema, the model's responses were unpredictable and hard to score. The code failures were almost entirely due to the model not accounting for string-formatted numbers. The next step was to enforce structured JSON output and add explicit instructions about common string-to-numeric patterns.

---

### V2 — Structured JSON Output + Local RAG Rulebook

**Change:** Added `response_format={"type": "json_object"}` to enforce a consistent schema (`{issues: [...], cleaning_code: str, summary: str}`). Added the local TF-IDF rulebook that retrieves the top-6 most relevant data engineering rules based on the column names and types in the dataset. The system prompt was rewritten to explicitly instruct the model to only report issues that are actually present, name the exact column affected, and handle string-formatted numbers before type conversion.

**Motivating example:** On `sales_dirty.csv`, V1 missed the revenue column entirely because it was stored as `"$12,500.00"` (a string with both a dollar sign and a comma). The rulebook rule `tc_002` ("Remove currency symbols and commas before numeric conversion") was retrieved and injected into the prompt, which caused the model to correctly identify the issue and generate `df['revenue'].str.replace(r'[$,]', '', regex=True)` before calling `pd.to_numeric`.

**Delta:** data_quality_score improved from 0.38 → 0.67. Issue detection improved from ~45% to ~72% of expected keywords found. Code runnability improved from 30% to 70% (7/10 test cases ran without errors). The structured JSON also made the frontend rendering reliable.

**Conclusion:** The rulebook retrieval had a measurable positive effect on currency and type-coercion cases. The structured output format eliminated parsing failures entirely. Remaining failures were mostly on edge cases like encoding artifacts in the logs CSV and the mixed-unit inventory CSV. The next step was to add code execution validation so the app could detect and report code failures before the user tries to run them.

---

### V3 — Subprocess Code Execution Sandbox + Follow-up Chat

**Change:** Added `backend/code_runner.py`, which executes the generated cleaning code in an isolated subprocess with a 15-second timeout. The Flask `/api/run-code` endpoint now returns whether the code succeeded or failed, along with stderr output. Added the follow-up chat feature (`/api/chat`) so users can ask clarifying questions. The system prompt was further refined to always produce a `df_cleaned` variable and to include `errors='coerce'` on all type conversion calls.

**Motivating example:** On `inventory_dirty.csv`, V2 generated code that called `df['quantity'].astype(int)` on a column containing the Unicode minus sign `−` (U+2212) instead of a regular hyphen `-`. This caused a `ValueError` at runtime. The subprocess sandbox caught this error and returned it to the frontend. This failure was then used to refine the prompt to instruct the model to use `pd.to_numeric(..., errors='coerce')` instead of `.astype(int)` for any numeric conversion.

**Delta:** data_quality_score improved from 0.67 → 0.81. Code runnability improved from 70% to 90% (9/10 test cases). The one remaining failure was the logs CSV with encoding artifacts, which required more sophisticated text cleaning than the model generated. Issue detection held steady at ~72%.

**Conclusion:** The code execution sandbox was the most impactful single change for the code runnability metric. Knowing that code will be validated pushed the prompt toward safer patterns (`errors='coerce'`, `str.strip()`, explicit null checks). The follow-up chat added significant usability value — users could ask "why does this code use fillna?" and get a clear explanation. Next steps would include a retry loop where the model sees its own code's error and attempts a fix, and better handling of non-ASCII characters in string columns.

---

## 3. Code Walkthrough

**Tracing a user action: uploading a CSV and clicking "Analyze Dataset"**

1. **`static/js/app.js` (handleAnalyze, line ~100):** The user clicks the Analyze button. The handler reads `state.csvText` (populated when the file was dropped onto the drop zone) and POSTs it as JSON to `/api/analyze`. A loading spinner is shown by calling `setLoading(dom.analyzeBtn, true)`.

2. **`app.py` (analyze route, line ~75):** Flask receives the POST. It extracts `csv_text` from the JSON body and calls `profile_csv(csv_text)` from `backend/profiler.py`.

3. **`backend/profiler.py` (profile_csv, line ~25):** Pandas parses the CSV text via `pd.read_csv(io.StringIO(csv_text))`. The function computes per-column stats (null counts, unique counts, dtype labels, sample values), counts duplicate rows with `df.duplicated().sum()`, and builds a `raw_summary` string. This returns a structured dict.

4. **`app.py` (analyze route, line ~95):** The profile's column names and types are joined into a query string and passed to `retrieve_rules(query, top_k=6)` in `backend/rulebook.py`. TF-IDF cosine similarity selects the 6 most relevant rules from `data/rulebook.json`.

5. **`backend/ai_engine.py` (analyze_dataset, line ~60):** The profile JSON and rulebook rules are injected into a structured prompt. `client.chat.completions.create()` is called with `model="gpt-4o-mini"` and `response_format={"type": "json_object"}`. The response is parsed and validated.

6. **`app.py` (analyze route, line ~105):** The session ID, profile, issues, and cleaning code are returned as JSON. The CSV text is saved to a temp directory keyed by session ID for later use by `/api/run-code`.

7. **`static/js/app.js` (renderResults, line ~155):** The frontend renders the profile table, issue cards (sorted by severity), and the code block. The code block is `contenteditable` so users can edit it before running.

**Design decision:** I used `response_format={"type": "json_object"}` instead of parsing free-text output. The alternative was regex extraction of code blocks and bullet lists, which I rejected because it broke on any variation in the model's phrasing. Structured JSON made the frontend rendering deterministic and eliminated an entire class of parsing bugs.

---

## 4. Conclusion

CSV Doctor demonstrates that a retrieval-augmented, multi-step AI workflow significantly outperforms a single extraction call for data quality analysis. The three main levers that improved the eval score were: enforcing structured JSON output (eliminated parsing failures), injecting relevant rulebook rules (improved detection of currency and type-coercion issues), and adding a code execution sandbox (caught runtime errors and drove safer code generation patterns).

The final data_quality_score of ~0.81 reflects that the app reliably identifies the most common data quality issues and generates code that runs correctly in 9 out of 10 test cases. The remaining gap is mostly in edge cases: non-ASCII characters, highly ambiguous column names, and datasets where the dominant issue is not covered by the rulebook.

If I were to continue, the highest-value next step would be a self-correction loop: when the sandbox detects a code error, feed the error message back to the model and ask it to fix the code. This would likely push code runnability to 100% on most cases. I would also expand the rulebook with more rules about encoding normalization and add a few-shot examples to the system prompt for the most common failure patterns.
