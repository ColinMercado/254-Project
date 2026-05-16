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
    # Pre-process the code to fix the most common AI-generated anti-patterns
    code = _sanitize_code(code)
    code = _fix_indentation(code)
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

# Allow boolean indexing with NA values (fills NA as False, keeps row out)
pd.options.mode.use_inf_as_na = True

# Load the dataset
df = pd.read_csv({repr(csv_tmp)})

# Safety helper: safe numeric conversion that never raises on bad values
def _safe_numeric(series):
    return pd.to_numeric(series, errors='coerce')

# Safety helper: safe datetime conversion that never raises on bad values
def _safe_datetime(series, **kwargs):
    kwargs.setdefault('errors', 'coerce')
    return pd.to_datetime(series, **kwargs)

# Safety helper: safe boolean mask that treats NaN as False
def _safe_mask(series):
    return series.fillna(False).astype(bool)

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


def _fix_indentation(code: str) -> str:
    """
    Normalize indentation in AI-generated code to prevent IndentationError.

    The model sometimes produces top-level statements with unexpected leading
    whitespace, or mixes tabs and spaces. This function:
    1. Converts all tabs to 4 spaces
    2. Detects lines that are at the top level of a block but have unexpected
       indentation (i.e. not inside an if/for/with/def/try block) and strips it
    """
    import textwrap

    # Step 1: normalize tabs → spaces
    code = code.replace('\t', '    ')

    # Step 2: use textwrap.dedent to remove any common leading whitespace
    # that the model added to the entire block
    code = textwrap.dedent(code)

    # Step 3: walk line by line and fix orphaned indented lines.
    # An "orphaned" line is one that is indented but the previous non-empty
    # line didn't open a block (doesn't end with ':').
    BLOCK_OPENERS = ('if ', 'elif ', 'else:', 'for ', 'while ', 'with ',
                     'def ', 'class ', 'try:', 'except', 'finally:')

    lines = code.splitlines()
    fixed = []
    prev_opens_block = False

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if not stripped:
            # Blank line — keep as-is, doesn't affect block state
            fixed.append(line)
            prev_opens_block = False
            continue

        if indent > 0 and not prev_opens_block:
            # This line is indented but the previous line didn't open a block.
            # Strip the indentation to bring it back to the top level.
            line = stripped

        fixed.append(line)

        # Determine if this line opens a new block
        prev_opens_block = stripped.rstrip().endswith(':') and any(
            stripped.startswith(kw) for kw in BLOCK_OPENERS
        )

    return '\n'.join(fixed)


def _sanitize_code(code: str) -> str:
    """
    Rewrite common AI-generated anti-patterns that cause runtime errors.

    Fixes:
    - `~df['col'].isna()` → `df['col'].notna()`
    - `~df['col'].isnull()` → `df['col'].notnull()`
    - `~df['col'].notna()` → `df['col'].isna()`
    - `~df['col'].notnull()` → `df['col'].isnull()`
    - `.astype(int)` on potentially-null columns → `.astype('Int64')`

    NOTE: We intentionally do NOT rewrite comparison filters like df[df['col'] > 0]
    because that regex is too broad and corrupts .loc[] assignments. The wrapper
    preamble sets pd.options.mode.use_inf_as_na = True and the prompt instructs
    the model to .fillna() before filtering, which handles this at the source.
    """
    import re

    # Pattern: ~df[...].isna() → df[...].notna()
    code = re.sub(
        r'~\s*([\w_]+\[[\'"]\w+[\'"]\])\.isna\(\)',
        r'\1.notna()',
        code,
    )
    # Pattern: ~df[...].isnull() → df[...].notnull()
    code = re.sub(
        r'~\s*([\w_]+\[[\'"]\w+[\'"]\])\.isnull\(\)',
        r'\1.notnull()',
        code,
    )
    # Pattern: ~df[...].notna() → df[...].isna()
    code = re.sub(
        r'~\s*([\w_]+\[[\'"]\w+[\'"]\])\.notna\(\)',
        r'\1.isna()',
        code,
    )
    # Pattern: ~df[...].notnull() → df[...].isnull()
    code = re.sub(
        r'~\s*([\w_]+\[[\'"]\w+[\'"]\])\.notnull\(\)',
        r'\1.isnull()',
        code,
    )

    # Pattern: .astype(int) → .astype('Int64')  (pandas nullable integer handles NaN)
    # Only replace bare .astype(int), not .astype('int64') or similar strings
    code = re.sub(r'\.astype\(\s*int\s*\)', ".astype('Int64')", code)

    return code
