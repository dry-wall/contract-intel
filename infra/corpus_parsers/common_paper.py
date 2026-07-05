"""
Parses a Common Paper standard-terms markdown file into top-level clauses.
Top-level clauses are lines with NO leading whitespace matching '<N>. ...';
everything until the next such line (or EOF) is that clause's body. Handles
both formatting styles seen across github.com/CommonPaper/*:
  - "N. **Heading**. body text..."                        (Mutual-NDA style)
  - 'N. <span class="header_2">Heading</span>  body...'   (CSA/DPA/PSA/SLA style)

Source: Common Paper's standard-terms GitHub repos, CC BY 4.0, drafted by
practicing attorneys. This is the BASELINE / market-standard corpus that
Phase 5's risk-scoring tool retrieves against to measure deviation.
"""
import re

TOP_LEVEL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
TAG_RE = re.compile(r"<[^>]+>")
MD_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")


def clean_text(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = MD_BOLD_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_heading(first_raw_line: str) -> str:
    """Heading comes from the FIRST LINE only, not the full clause body."""
    clean_first_line = clean_text(first_raw_line)
    clean_first_line = re.sub(r"^\d+\.\s*", "", clean_first_line)
    m = re.match(r"([^.]{2,80})\.\s+\S", clean_first_line)
    if m:
        # Mutual-NDA style: "Introduction. This MNDA allows..." -> "Introduction"
        return m.group(1).strip()
    # header_2 style: the whole first line IS just the heading.
    return clean_first_line.rstrip(".").strip()[:80]


def parse_clauses(md_text: str, source_name: str) -> list[dict]:
    """Returns unified-schema dicts: clause_type, clause_text, source."""
    lines = md_text.splitlines()
    clauses = []
    current_lines: list[str] = []

    def flush():
        if not current_lines:
            return
        raw = "\n".join(current_lines)
        cleaned = clean_text(raw)
        if len(cleaned) < 20:  # skip near-empty fragments
            return
        heading = extract_heading(current_lines[0])
        clauses.append({"clause_type": heading, "clause_text": cleaned, "source": source_name})

    for line in lines:
        if line.startswith(" ") or line.startswith("\t"):
            current_lines.append(line)  # indented -> sub-item of current clause
            continue
        if TOP_LEVEL_RE.match(line):
            flush()
            current_lines = [line]
        elif current_lines:
            current_lines.append(line)
    flush()
    return clauses
