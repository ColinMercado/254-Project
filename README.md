# CSV Doctor

**AI-powered data quality diagnosis for messy CSV files.**

Upload or paste a CSV dataset and CSV Doctor will profile it, identify data quality issues (missing values, duplicates, type mismatches, invalid dates, outliers, and more), explain each problem in plain English, and generate runnable Python/Pandas cleaning code, all powered by the OpenAI API.

Built for data engineering students who want to understand *what's wrong* with a dataset before using it in a pipeline or analysis project.

---

## What It Does

1. **Profile** — Computes shape, column types, null counts, duplicate rows, and sample values
2. **Diagnose** — Uses GPT-4o-mini + a local data engineering rulebook to identify issues
3. **Prescribe** — Generates complete, runnable Pandas cleaning code
4. **Validate** — Executes the code in a sandbox and lets you download the cleaned CSV
5. **Loop** — Click **Analyze Again** after a successful run to re-diagnose the cleaned dataset without re-uploading, repeating the cycle until the data is clean
6. **Explain** — Follow up chat so you can ask "why?" or "make this simpler"

---

## Prerequisites

- Python 3.11 or higher
- `pip`
- An OpenAI API key ([get one here](https://platform.openai.com/api-keys))

---

## Setup

**1. Clone the repository**

```bash
git clone <your-repo-url>
cd 254-Project
```

**2. Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure your API key**

```bash
cp .env.example .env
```

Open `.env` and add your key:

```
OPENAI_API_KEY=sk-...your-key-here...
```

---

## Running the App

```bash
python app.py
```

Then open your browser to: **http://localhost:5000**

You should see the CSV Doctor interface. Upload a CSV file or paste CSV text, then click **Analyze Dataset**.

---

## Example Invocations

**Upload a file and run the cleaning loop:**
1. Click "Upload File" tab
2. Drag `eval/test_csvs/customers_dirty.csv` onto the drop zone (or click to browse)
3. Click **Analyze Dataset**
4. Review the issues panel, you should see: duplicate IDs, missing emails, inconsistent date formats, age stored as text
5. Click **Run Code** to execute the generated cleaning code
6. On success, click **Analyze Again** to re-diagnose the cleaned dataset, no re-uploading needed
7. Repeat steps 5–6 until the diagnosis shows no remaining issues
8. Click **Download Cleaned CSV** at any point to save the current cleaned version

**Paste CSV:**
1. Click "Paste CSV" tab
2. Paste this sample:
   ```
   id,name,email,age
   1,Alice,alice@example.com,25
   2,Bob,,thirty
   1,Alice,alice@example.com,25
   ```
3. Click **Analyze Dataset**

**Follow-up chat:**
After analysis, scroll to the chat section and ask:
- "Why should I convert the age column to numeric?"
- "Can you make the cleaning code simpler?"
- "What does fillna do?"

---

## Running the Evaluation

Make sure the Flask app is running first (`python app.py`), then in a separate terminal:

```bash
python eval/eval.py
```

For verbose output showing full AI responses:

```bash
python eval/eval.py --verbose
```

To run against a different server URL:

```bash
python eval/eval.py --url http://localhost:5000
```

The eval script runs all 10 test cases and prints a results table. Results are saved to `eval/results.json`.

**Eval metric:**
```
data_quality_score = (correctly_identified_issues + runnable_cleaning_steps)
                     / (total_expected_issues + total_expected_steps)
```

---

## Project Structure

```
254-Project/
├── app.py                      # Flask application (routes)
├── requirements.txt            # Pinned Python dependencies
├── .env.example                # Copy to .env and add your API key
├── README.md
├── REPORT.md
│
├── backend/
│   ├── __init__.py
│   ├── profiler.py             # CSV profiling with pandas
│   ├── rulebook.py             # Local RAG (TF-IDF over rulebook.json)
│   ├── ai_engine.py            # OpenAI API calls
│   └── code_runner.py          # Subprocess sandbox for code execution
│
├── data/
│   └── rulebook.json           # 20 data engineering rules for RAG
│
├── static/
│   ├── css/style.css           # App styles
│   └── js/app.js               # Frontend logic (vanilla JS)
│
├── templates/
│   └── index.html              # Single-page HTML template
│
└── eval/
    ├── eval.py                 # Evaluation script
    ├── test_cases.json         # 10 labeled test cases
    └── test_csvs/              # Dirty CSV files for testing
        ├── customers_dirty.csv
        ├── orders_dirty.csv
        └── ...
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `FLASK_DEBUG` | No | Set to `true` for debug mode |
| `PORT` | No | Server port (default: 5000) |

---

## Troubleshooting

**"OPENAI_API_KEY is not set"** — Make sure you copied `.env.example` to `.env` and added your key.

**"Could not parse CSV"** — Check that your file uses comma separators and has a header row.

**"Code execution timed out"** — The generated code took more than 15 seconds. Try clicking Run Code again or ask the chat to simplify the code.

**Port already in use** — Run `PORT=5001 python app.py` to use a different port.
