"""
backend/rulebook.py

Local data engineering rulebook with TF-IDF-based retrieval.
No external vector DB required — everything runs in-memory using scikit-learn.
"""

import json
import os
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# Module-level cache so we only build the index once per process
_rules: List[dict] = []
_vectorizer: TfidfVectorizer | None = None
_tfidf_matrix = None


def load_rulebook(path: str | None = None) -> List[dict]:
    """
    Load rules from the JSON rulebook file.
    Defaults to data/rulebook.json relative to the project root.
    """
    global _rules, _vectorizer, _tfidf_matrix

    if path is None:
        # Resolve relative to this file's location (backend/ → project root → data/)
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "..", "data", "rulebook.json")

    with open(path, "r", encoding="utf-8") as f:
        _rules = json.load(f)

    # Build TF-IDF index over rule content + title
    corpus = [f"{r['title']} {r['content']}" for r in _rules]
    _vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    _tfidf_matrix = _vectorizer.fit_transform(corpus)

    return _rules


def retrieve_rules(query: str, top_k: int = 5) -> str:
    """
    Retrieve the top-k most relevant rules for a given query using
    TF-IDF cosine similarity.

    Returns a formatted numbered list string ready for injection into
    an AI prompt.
    """
    global _rules, _vectorizer, _tfidf_matrix

    # Lazy-load if not yet initialized
    if not _rules or _vectorizer is None:
        load_rulebook()

    if not _rules:
        return "No rulebook rules available."

    # Vectorize the query and compute similarities
    query_vec = _vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, _tfidf_matrix).flatten()

    # Get top-k indices (sorted descending)
    top_indices = np.argsort(similarities)[::-1][:top_k]

    # Filter out rules with zero similarity (completely irrelevant)
    relevant = [i for i in top_indices if similarities[i] > 0.0]

    if not relevant:
        # Fall back to first top_k rules if nothing matches
        relevant = list(range(min(top_k, len(_rules))))

    lines = ["Relevant data engineering rules from the rulebook:"]
    for rank, idx in enumerate(relevant, 1):
        rule = _rules[idx]
        lines.append(f"\n{rank}. [{rule['category'].upper()}] {rule['title']}")
        lines.append(f"   {rule['content']}")

    return "\n".join(lines)


def get_all_rules() -> List[dict]:
    """Return all loaded rules (useful for debugging)."""
    if not _rules:
        load_rulebook()
    return _rules
