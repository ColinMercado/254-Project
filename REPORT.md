# REPORT.md — CSV Doctor

---

## 1. What & Why

CSV Doctor is an AI-powered web application that helps data engineering students diagnose and clean messy CSV datasets. A user uploads or pastes a CSV file, and the app profiles the data, identifies quality issues, explains each problem in plain English, generates runnable Python/Pandas cleaning code, and supports follow up questions through a chat interface.

The target audience is students like me who are learning data engineering and regularly encounter real world datasets that are far from clean. Before building a pipeline or running analysis, you need to know what is wrong with the data, but beginners often do not know what to look for or how to fix it. CSV Doctor acts as a knowledgeable assistant that walks through the dataset and explains every problem it finds.

Getting the AI behavior right is genuinely hard for several reasons. First, the model must only report issues that are actually present in the data, hallucinating problems that do not exist is worse than missing a real one, because it erodes trust. Second, the generated Pandas code must actually run without errors on the specific CSV provided, not just look plausible. Third, the explanations must be accurate and beginner friendly at the same time, which requires the model to calibrate its language to the audience. Finally, different datasets have different dominant issues, so a single rigid prompt tends to miss edge cases like currency formatted numbers, mixed date formats, or encoding artifacts. These challenges make this problem a good fit for a retrieval augmented, iterative AI workflow rather than a single extraction call.

---

## 2. Iterations

### V1 — Baseline: Single Prompt, No RAG, No Code Validation

**Change:** The initial version sent the dataset profile directly to GPT-4o-mini with a simple system prompt asking it to list issues and generate cleaning code. No rulebook, no structured output format, no code execution.

**Motivating example:** On `orders_dirty.csv`, the model returned a free text paragraph that mentioned "some price formatting issues" without specifying the column name or the dollar sign pattern. The generated code used `df['price'].astype(float)` directly, which crashed because the values contained `$` characters. The eval script could not parse the response reliably because the output format varied between runs.

**Delta:** data_quality_score = 0.38 (baseline). Issue detection was inconsistent, the model sometimes invented issues not present in the data, and the free text format made keyword matching unreliable. Code runnability was 3/10 (30%) because most generated code assumed clean numeric types.

**Conclusion:** The free text output format was the biggest problem. Without a schema, the model's responses were unpredictable and hard to score. The code failures were almost entirely due to the model not accounting for string formatted numbers. The next step was to enforce structured JSON output and add explicit instructions about common string to numeric patterns.

---

### V2 — Structured JSON + RAG Rulebook + Code Execution Sandbox

**Change:** Added `response_format={"type": "json_object"}` to enforce a consistent schema (`{issues: [...], cleaning_code: str, summary: str}`). Added the local TF-IDF rulebook that retrieves the top 6 most relevant data engineering rules based on column names and types. Added `backend/code_runner.py`, which executes generated cleaning code in an isolated subprocess with a 15-second timeout and returns success/failure with stderr. The system prompt was rewritten with explicit safety rules: always use `pd.to_numeric(..., errors='coerce')` instead of `.astype(int)`, always use `errors='coerce'` with `pd.to_datetime()`, and always produce a `df_cleaned` variable.

**Motivating example:** On `sales_dirty.csv`, V1 missed the revenue column stored as `"$12,500.00"` and generated `df['price'].astype(float)` which crashed on dollar signs. The rulebook rule for currency normalization caused the model to generate `df['revenue'].str.replace(r'[$,]', '', regex=True)` before `pd.to_numeric`. Separately, on `inventory_dirty.csv`, the model generated `.astype(int)` on a column containing the Unicode minus sign `−`, which the sandbox caught and surfaced as a clear error message.

**Delta:** data_quality_score improved from 0.38 to 0.81. Issue detection improved from ~45% to ~72%. Code runnability improved from 30% to 90% (9/10 test cases). The structured JSON eliminated all parsing failures on the frontend.

**Conclusion:** Combining structured output, RAG, and code validation in one iteration produced the largest single jump in the metric. The rulebook retrieval most helped currency and type coercion cases. The sandbox made code failures visible and drove safer prompt patterns. The remaining 10% failure was the logs CSV with encoding artifacts.

---

### V3 — Iterative Cleaning Loop + Code Sanitizer + Indentation Fixer

**Change:** Added an **Analyze Again** button that appears after a successful code run. It fetches the cleaned CSV already stored on the server and sends it straight back to `/api/analyze`, letting users run multiple diagnosis clean rediagnose cycles without re-uploading. Added `_sanitize_code()` in `code_runner.py` to rewrite unsafe patterns before execution (e.g. `~df['col']` on float columns `.notna()`), and `_fix_indentation()` to normalize tabs/spaces and strip orphaned indentation that the model occasionally generates. Also added `pd.options.mode.use_inf_as_na = True` to the subprocess preamble so NaN values in boolean masks don't crash comparison filters.

**Motivating example:** After the first cleaning pass on a customer dataset, the re-analysis found a remaining outlier issue in the `age` column. The model generated `df_cleaned.loc[df_cleaned['age'] == 0.0, 'age'] = pd.NA` but an earlier sanitizer regex was corrupting `.loc[]` assignments into `loc[df_cleaned['age']]`, causing a `NameError`. The fix was to remove the overly broad comparison rewriting regex and rely on the prompt rules and preamble instead.

**Delta:** data_quality_score on multi pass runs improved from effectively 0 (second pass always errored) to matching the first pass score of ~0.81. Single pass score held steady. The indentation fixer eliminated a class of `IndentationError` failures that appeared on second pass analyses where the model generated slightly different code structure.

**Conclusion:** The iterative loop is the most user facing improvement, it turns CSV Doctor from a one shot tool into a genuine cleaning workflow. The sanitizer and indentation fixer address the long tail of code generation edge cases. Next steps would include a self correction loop where the model sees its own error and retries automatically, and expanding the rulebook with encoding normalization rules.

---

## 3. Code Walkthrough

**Tracing a user action: uploading a CSV and clicking "Analyze Dataset"**

1. **`static/js/app.js` (handleAnalyze, line ~100):** The user clicks the Analyze button. The handler reads `state.csvText` (populated when the file was dropped onto the drop zone) and POSTs it as JSON to `/api/analyze`. A loading spinner is shown by calling `setLoading(dom.analyzeBtn, true)`.

2. **`app.py` (analyze route, line ~75):** Flask receives the POST. It extracts `csv_text` from the JSON body and calls `profile_csv(csv_text)` from `backend/profiler.py`.

3. **`backend/profiler.py` (profile_csv, line ~25):** Pandas parses the CSV text via `pd.read_csv(io.StringIO(csv_text))`. The function computes per column stats (null counts, unique counts, dtype labels, sample values), counts duplicate rows with `df.duplicated().sum()`, and builds a `raw_summary` string. This returns a structured dict.

4. **`app.py` (analyze route, line ~95):** The profile's column names and types are joined into a query string and passed to `retrieve_rules(query, top_k=6)` in `backend/rulebook.py`. TF-IDF cosine similarity selects the 6 most relevant rules from `data/rulebook.json`.

5. **`backend/ai_engine.py` (analyze_dataset, line ~60):** The profile JSON and rulebook rules are injected into a structured prompt. `client.chat.completions.create()` is called with `model="gpt-4o-mini"` and `response_format={"type": "json_object"}`. The response is parsed and validated.

6. **`app.py` (analyze route, line ~105):** The session ID, profile, issues, and cleaning code are returned as JSON. The CSV text is saved to a temp directory keyed by session ID for later use by `/api/run-code`.

7. **`static/js/app.js` (renderResults, line ~155):** The frontend renders the profile table, issue cards (sorted by severity), and the code block. The code block is `contenteditable` so users can edit it before running.

**Design decision:** I used `response_format={"type": "json_object"}` instead of parsing free text output. The alternative was regex extraction of code blocks and bullet lists, which I rejected because it broke on any variation in the model's phrasing. Structured JSON made the frontend rendering deterministic and eliminated an entire class of parsing bugs.

---


## 4. AI Disclosure & Safety

Kiro was used as the primary coding assistant throughout this project, handling scaffolding, backend logic, and the frontend layout. It was useful for generating boilerplate quickly, but several specific failures required manual diagnosis and recovery.

**Failure 1 — Broken code generation patterns.** The model repeatedly generated Pandas code that crashed at runtime. The first instance was `~df['col']` applied directly to a float column, which raises `TypeError: bad operand type for unary ~: 'float'` because the bitwise NOT operator requires a boolean Series. The second was `df[df['col'] > 0]` used immediately after `pd.to_numeric(..., errors='coerce')`, which leaves NaN values in the column, pandas cannot use a mask containing NaN, raising `ValueError: Cannot mask with non-boolean array containing NA / NaN values`. Recovery required adding explicit safety rules to the system prompt (e.g. "always `.fillna()` before a comparison filter") and a `_sanitize_code()` pre processor in `code_runner.py` that rewrites the tilde pattern before execution.

**Failure 2 — Sanitizer regex corrupting valid code.** A regex added to fix the NaN mask problem was written too broadly. It matched `df_cleaned.loc[df_cleaned['age'] == 0.0, 'age']` and corrupted it into `loc[df_cleaned['age']] == 0.0, 'age').fillna(False)`, producing a `NameError: name 'loc' is not defined`. The fix was to remove the comparison rewriting regex entirely and rely on the prompt rules and the `pd.options.mode.use_inf_as_na = True` preamble instead.

**Failure 3 — Indentation errors on second-pass analysis.** After clicking Analyze Again, the model occasionally generated top level statements with unexpected leading whitespace, causing `IndentationError: unexpected indent`. This did not appear on first pass runs because the model produced slightly different code structure when the input dataset was already partially cleaned. Recovery required adding `_fix_indentation()` in `code_runner.py`, which applies `textwrap.dedent` and then strips orphaned indentation from lines whose preceding statement did not open a block.

**Safety risk — prompt injection via the chat interface.** Because the follow up chat sends user supplied text directly into an LLM prompt, a user could attempt to override the system instructions and use the model as a general purpose assistant, bypassing the intended scope. The mitigation is two layered: a keyword based pre-check in `backend/ai_engine.py` rejects messages longer than four words that contain no data engineering related terms before any API call is made, and the system prompt explicitly instructs the model to refuse off topic questions and treat override phrases like "ignore previous instructions" as injection attempts. The accepted limit is that a sufficiently creative rephrasing could still slip through the keyword filter; a more robust solution would use a separate classification call, but that doubles API cost per message.
