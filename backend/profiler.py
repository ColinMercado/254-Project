"""
backend/profiler.py

Pandas-based CSV profiler. Computes dataset statistics used to build
the AI analysis prompt.
"""

import io
import json
import pandas as pd
import numpy as np


# Maximum rows to profile (keeps prompt size manageable)
MAX_ROWS = 1000


def profile_csv(csv_text: str) -> dict:
    """
    Parse CSV text and return a structured profile dict.

    Returns a dict with keys:
        - error (str): present only if parsing failed
        - shape: {rows, cols}
        - columns: list of per-column stats
        - duplicate_rows: int
        - sample: list of up to 5 row dicts
        - raw_summary: human-readable string for the AI prompt
    """
    # --- Parse ---
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as exc:
        return {"error": f"Could not parse CSV: {exc}"}

    if df.empty:
        return {"error": "The CSV file is empty or has no data rows."}

    # Truncate for profiling
    truncated = len(df) > MAX_ROWS
    df_profile = df.head(MAX_ROWS).copy()

    total_rows = len(df)
    total_cols = len(df.columns)

    # --- Per-column stats ---
    columns = []
    for col in df_profile.columns:
        series = df_profile[col]
        null_count = int(series.isna().sum())
        null_pct = round(null_count / len(df_profile) * 100, 1) if len(df_profile) > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))

        # Sample up to 5 non-null values
        non_null = series.dropna()
        sample_values = [_safe_val(v) for v in non_null.head(5).tolist()]

        # Infer a friendlier type label
        dtype_label = _dtype_label(series)

        columns.append({
            "name": col,
            "dtype": dtype_label,
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
            "sample_values": sample_values,
        })

    # --- Duplicate rows ---
    duplicate_rows = int(df_profile.duplicated().sum())

    # --- Sample rows (up to 5) ---
    sample_rows = []
    for _, row in df_profile.head(5).iterrows():
        sample_rows.append({col: _safe_val(v) for col, v in row.items()})

    # --- Raw summary string for AI prompt ---
    raw_summary = _build_summary(
        total_rows, total_cols, truncated, columns, duplicate_rows, sample_rows
    )

    return {
        "shape": {"rows": total_rows, "cols": total_cols},
        "columns": columns,
        "duplicate_rows": duplicate_rows,
        "sample": sample_rows,
        "raw_summary": raw_summary,
        "truncated": truncated,
    }


def _dtype_label(series: pd.Series) -> str:
    """Return a human-friendly dtype label."""
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    # For object columns, try to detect if they look numeric or date-like
    if dtype == object:
        non_null = series.dropna().astype(str)
        if len(non_null) == 0:
            return "string (all null)"
        # Check if it looks numeric (possibly with currency symbols)
        cleaned = non_null.str.replace(r"[$,\s]", "", regex=True)
        numeric_ratio = pd.to_numeric(cleaned, errors="coerce").notna().mean()
        if numeric_ratio > 0.8:
            return "string (looks numeric)"
        # Check if it looks like dates
        date_ratio = pd.to_datetime(non_null, errors="coerce", infer_datetime_format=True).notna().mean()
        if date_ratio > 0.7:
            return "string (looks like date)"
        return "string"
    return str(dtype)


def _safe_val(v):
    """Convert numpy/pandas types to JSON-serializable Python types."""
    if pd.isna(v) if not isinstance(v, (list, dict)) else False:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _build_summary(total_rows, total_cols, truncated, columns, duplicate_rows, sample_rows) -> str:
    """Build a concise text summary for injection into the AI prompt."""
    lines = []
    lines.append(f"Dataset shape: {total_rows} rows × {total_cols} columns")
    if truncated:
        lines.append(f"(Note: profiling was performed on the first {MAX_ROWS} rows)")
    lines.append(f"Duplicate rows: {duplicate_rows}")
    lines.append("")
    lines.append("Column details:")
    for col in columns:
        lines.append(
            f"  - {col['name']}: type={col['dtype']}, "
            f"nulls={col['null_count']} ({col['null_pct']}%), "
            f"unique={col['unique_count']}, "
            f"samples={col['sample_values']}"
        )
    lines.append("")
    lines.append("Sample rows (first 5):")
    for i, row in enumerate(sample_rows, 1):
        lines.append(f"  Row {i}: {json.dumps(row)}")
    return "\n".join(lines)
