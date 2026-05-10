"""
backend/code_runner.py

Subprocess sandbox for executing AI-generated Pandas cleaning code.
Runs code in an isolated process with a timeout to prevent hangs or crashes
from affecting the main Flask server.
"""

import os
import sys
import subprocess
import tempfile
import textwrap
from typing import Optional


TIMEOUT_SECONDS = 15


def run_cleaning_code(csv_text: str, code: str) -> dict:
    """
    Execute AI-generated Pandas cleaning code against the provided CSV data.

    The code is expected to:
    - Receive a DataFrame named `df` (pre-loaded from the CSV)
    - Produce a cleaned DataFrame named `df_cleaned`

    Args:
        csv_text: Raw CSV content as a string
        code: Python/Pandas cleaning code to execute

    Returns:
        dict with keys:
            - success (bool): True if code ran without errors
            - error (str | None): Error message if failed
            - cleaned_csv (str | None): Cleaned CSV content if successful
            - stdout (str): Any print output from the code
    """
    csv_tmp = None
    out_tmp = None
    script_tmp = None

    try:
        # Write the CSV to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_text)
            csv_tmp = f.name

        # Temp file for the cleaned output
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            out_tmp = f.name

        # Build the wrapper script
        # We inject the CSV path and output path as string literals so the
        # subprocess doesn't need any arguments.
        wrapper = textwrap.dedent(f"""
import pandas as pd
import numpy as np
import sys
import warnings
warnings.filterwarnings('ignore')

# Load the dataset
df = pd.read_csv({repr(csv_tmp)})

# ---- User cleaning code ----
{code}
# ---- End user code ----

# Save the cleaned dataset
if 'df_cleaned' in dir():
    df_cleaned.to_csv({repr(out_tmp)}, index=False)
    print("__CLEANED_CSV_SAVED__")
else:
    # If no df_cleaned was created, save df as-is
    df.to_csv({repr(out_tmp)}, index=False)
    print("__NO_DF_CLEANED_USING_DF__")
""")

        # Write the wrapper script to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(wrapper)
            script_tmp = f.name

        # Execute in a subprocess using the same Python interpreter
        result = subprocess.run(
            [sys.executable, script_tmp],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            # Code raised an exception
            error_msg = _extract_error(stderr)
            return {
                "success": False,
                "error": error_msg,
                "cleaned_csv": None,
                "stdout": stdout,
            }

        # Read the cleaned CSV
        cleaned_csv: Optional[str] = None
        if os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            with open(out_tmp, "r", encoding="utf-8") as f:
                cleaned_csv = f.read()

        # Remove internal sentinel from stdout before returning
        display_stdout = stdout.replace("__CLEANED_CSV_SAVED__", "").replace(
            "__NO_DF_CLEANED_USING_DF__", ""
        ).strip()

        return {
            "success": True,
            "error": None,
            "cleaned_csv": cleaned_csv,
            "stdout": display_stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": (
                f"Code execution timed out after {TIMEOUT_SECONDS} seconds. "
                "The cleaning code may contain an infinite loop or very slow operation."
            ),
            "cleaned_csv": None,
            "stdout": "",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Unexpected error during code execution: {exc}",
            "cleaned_csv": None,
            "stdout": "",
        }
    finally:
        # Always clean up temp files
        for path in [csv_tmp, out_tmp, script_tmp]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def _extract_error(stderr: str) -> str:
    """
    Extract the most useful part of a Python traceback for display.
    Returns the last few lines which typically contain the actual error.
    """
    if not stderr:
        return "Unknown error (no stderr output)"

    lines = stderr.strip().splitlines()

    # Find the last "Error:" line for a clean message
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and ("Error" in stripped or "Exception" in stripped):
            # Return this line plus a few lines of context
            idx = lines.index(line)
            context_start = max(0, idx - 2)
            return "\n".join(lines[context_start:]).strip()

    # Fall back to last 5 lines
    return "\n".join(lines[-5:]).strip()
