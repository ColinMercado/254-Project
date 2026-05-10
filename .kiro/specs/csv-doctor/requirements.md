# CSV Doctor — Requirements

## Introduction
CSV Doctor is an AI-powered web application that helps data engineering students diagnose and clean messy CSV datasets. Users upload or paste CSV data, and the app profiles the dataset, identifies data quality issues, explains them in plain English, generates runnable Python/Pandas cleaning code, and supports follow-up questions.

## Requirements

### R1 — CSV Input
- **R1.1** The app shall accept CSV data via file upload (drag-and-drop or browse).
- **R1.2** The app shall accept CSV data via a paste-text textarea.
- **R1.3** The app shall validate that the input is parseable as CSV and display a clear error if not.
- **R1.4** The app shall support CSV files up to 5 MB.

### R2 — Dataset Profiling
- **R2.1** The app shall display the dataset shape (rows × columns).
- **R2.2** The app shall display column names, inferred data types, null counts, and null percentages.
- **R2.3** The app shall display the number of duplicate rows.
- **R2.4** The app shall display a sample of up to 5 rows.

### R3 — AI Issue Detection
- **R3.1** The app shall use the OpenAI API to analyze the dataset profile and identify data quality issues.
- **R3.2** The app shall detect at minimum: missing values, duplicate rows, type mismatches, inconsistent date formats, invalid values (negative quantities, malformed strings), and columns with suspicious patterns.
- **R3.3** Each identified issue shall include a plain-English explanation suitable for a beginner.
- **R3.4** The app shall use a local data engineering rulebook (RAG) to ground AI suggestions in established best practices.

### R4 — AI Cleaning Code Generation
- **R4.1** The app shall generate Python/Pandas code to address each identified issue.
- **R4.2** Generated code shall be self-contained and runnable given a DataFrame named `df`.
- **R4.3** The app shall validate generated code by executing it in a sandboxed subprocess.
- **R4.4** The app shall display whether the generated code ran successfully or show the error.
- **R4.5** The app shall allow the user to download the cleaned CSV produced by the generated code.

### R5 — Follow-up Chat
- **R5.1** The app shall provide a chat interface for follow-up questions about the dataset or generated code.
- **R5.2** The chat shall maintain conversation context (dataset profile + prior messages).
- **R5.3** Example follow-up questions: "Why should I convert this column to datetime?", "Make this code simpler."

### R6 — UI/UX
- **R6.1** The app shall display a loading/spinner state while AI calls are in progress.
- **R6.2** The app shall display user-friendly error messages for API failures, invalid input, and code execution errors.
- **R6.3** The UI shall be a single-page web app served by Flask.
- **R6.4** The UI shall be accessible (semantic HTML, ARIA labels, keyboard navigable).

### R7 — Eval & Reporting
- **R7.1** The repo shall include an `eval/` directory with an eval script and ≥10 labeled test cases.
- **R7.2** The eval metric is: `data_quality_score = (correctly_identified_issues + runnable_cleaning_steps) / (total_expected_issues + total_cleaning_steps)`.
- **R7.3** The repo shall include `REPORT.md` with four sections: What & why, Iterations (≥3), Code walkthrough, Conclusion.

### R8 — Setup & Distribution
- **R8.1** The repo shall include `requirements.txt` with pinned dependencies.
- **R8.2** The repo shall include `.env.example` containing only `OPENAI_API_KEY=`.
- **R8.3** The repo shall include `README.md` with step-by-step setup and run instructions.
- **R8.4** The app shall require only `OPENAI_API_KEY` to run; no other external services.
