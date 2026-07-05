"""
Parses CUAD's SQuAD-style JSON into normalized population clauses.
Each contract has ~41 "questions" (one per clause category); an answer
(non-empty) means that clause type is present in that contract, with the
answer text being the actual clause span. is_impossible=True / empty answers
means that category doesn't appear in this contract -> skipped.

Source: The Atticus Project's CUAD v1 (github.com/TheAtticusProject/cuad),
CC BY 4.0. 510 real commercial contracts (SEC filings), 41 clause categories,
13,000+ expert labels. This is the POPULATION reference — real-world clauses
as they actually appear "in the wild" — used for BigQuery benchmarking
(Phase 7) and, filtered differently, as additional retrieval context.
"""
import json
import re


def category_from_question(question: str) -> str:
    """
    CUAD questions look like:
    'Highlight the parts (if any) of this contract related to "Document Name"
     that should be reviewed by a lawyer. Details: ...'
    Extract the quoted category name.
    """
    m = re.search(r'related to \\"(.+?)\\"', question) or re.search(r'related to "(.+?)"', question)
    return m.group(1) if m else question[:40]


def parse_cuad(cuad_json_path: str, max_contracts: int | None = None) -> list[dict]:
    """Returns unified-schema dicts: clause_type, clause_text, source."""
    with open(cuad_json_path, encoding="utf-8") as f:
        data = json.load(f)

    clauses = []
    contracts = data["data"][:max_contracts] if max_contracts else data["data"]
    for contract in contracts:
        title = contract["title"]
        for paragraph in contract["paragraphs"]:
            for qa in paragraph["qas"]:
                answers = qa.get("answers", [])
                if not answers:
                    continue
                clause_type = category_from_question(qa["question"])
                # A category can have multiple non-contiguous spans; join them.
                text = " [...] ".join(a["text"].strip() for a in answers if a["text"].strip())
                text = re.sub(r"\s+", " ", text).strip()  # CUAD text has OCR whitespace artifacts
                if len(text) < 15:
                    continue
                clauses.append({"clause_type": clause_type, "clause_text": text, "source": title})
    return clauses
