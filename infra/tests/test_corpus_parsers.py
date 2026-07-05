"""
Fast, network-free tests for the corpus parsers. Uses small inline fixtures
rather than the real downloaded corpora — those are covered by actually
running infra/seed_corpus.py + embed_and_load.py (see Phase 4 guide), which
is slow and network-dependent and therefore not something to run on every
test invocation.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_parsers.common_paper import parse_clauses as parse_common_paper
from corpus_parsers.cuad import category_from_question, parse_cuad

# --- Common Paper parser: both real formatting styles ----------------------

MUTUAL_NDA_STYLE = """# Standard Terms

1. **Introduction**. This Mutual Non-Disclosure Agreement allows each party to disclose information.

2. **Exceptions**. The Receiving Party's obligations do not apply to information that is public.
"""

HEADER2_STYLE = """# Cloud Service Agreement

1. <span class="header_2" id="1">Service</span>
    1. <span class="header_3" id="1.1">Access and Use.</span>  During the Subscription Period, Customer may access the Product.
    2. <span class="header_3" id="1.2">Support.</span>  Provider will provide support.

2. <span class="header_2" id="2">Restrictions</span>
    1. Customer will not reverse engineer the Product.
"""


def test_parses_mutual_nda_style_headings():
    clauses = parse_common_paper(MUTUAL_NDA_STYLE, source_name="Test NDA")
    assert len(clauses) == 2
    assert clauses[0]["clause_type"] == "Introduction"
    assert clauses[1]["clause_type"] == "Exceptions"
    assert "Mutual Non-Disclosure" in clauses[0]["clause_text"]


def test_parses_header2_style_headings_and_includes_subitems():
    clauses = parse_common_paper(HEADER2_STYLE, source_name="Test CSA")
    assert len(clauses) == 2
    assert clauses[0]["clause_type"] == "Service"
    # Sub-items (Access and Use, Support) should be folded into the parent clause body.
    assert "Access and Use" in clauses[0]["clause_text"]
    assert "Support" in clauses[0]["clause_text"]
    assert clauses[1]["clause_type"] == "Restrictions"


def test_strips_html_tags_and_markdown_bold():
    clauses = parse_common_paper(HEADER2_STYLE, source_name="Test CSA")
    assert "<span" not in clauses[0]["clause_text"]
    assert "**" not in clauses[0]["clause_text"]


def test_skips_near_empty_fragments():
    tiny = "1. **X**. a.\n\n2. **Y**. b."
    clauses = parse_common_paper(tiny, source_name="Test Tiny")
    assert len(clauses) == 0  # both fragments are under the 20-char floor


# --- CUAD parser -------------------------------------------------------

def test_category_from_question_extracts_quoted_name():
    q = 'Highlight the parts (if any) of this contract related to "Governing Law" that should be reviewed.'
    assert category_from_question(q) == "Governing Law"


def test_parse_cuad_skips_empty_answers_and_normalizes_whitespace(tmp_path):
    fixture = {
        "version": "test",
        "data": [
            {
                "title": "TEST_CONTRACT",
                "paragraphs": [
                    {
                        "context": "irrelevant for this test",
                        "qas": [
                            {
                                "question": 'Highlight the parts related to "Governing Law" details.',
                                "answers": [{"text": "  This   Agreement   is governed by Delaware law.  ", "answer_start": 0}],
                                "id": "1",
                                "is_impossible": False,
                            },
                            {
                                "question": 'Highlight the parts related to "Exclusivity" details.',
                                "answers": [],
                                "id": "2",
                                "is_impossible": True,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    clauses = parse_cuad(str(fixture_path))
    assert len(clauses) == 1  # the empty-answer "Exclusivity" qa is skipped
    assert clauses[0]["clause_type"] == "Governing Law"
    assert clauses[0]["source"] == "TEST_CONTRACT"
    # Whitespace should be collapsed to single spaces.
    assert clauses[0]["clause_text"] == "This Agreement is governed by Delaware law."
