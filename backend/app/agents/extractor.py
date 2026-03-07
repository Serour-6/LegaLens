import json
import re
from typing import List, Dict, Any

from .backboard import backboard_save, backboard_get_global_law_context
from .llm import extractor_llm, call_llm


EXTRACTOR_PROMPT = """You are a legal clause extraction engine for Canadian contracts.

Canadian law context (use for relevance and clause types):
{canadian_law}

Read the document below and find every legal clause worth examining.
Output ONLY a valid JSON array. Each object must have exactly these fields:
- "id": unique string like "clause_001"
- "type": one of — Liability Waiver, IP Assignment, Non-Compete, Arbitration,
  Auto-Renewal, Data & Privacy, Termination for Cause, Indemnification,
  Force Majeure, Governing Law, Amendment / Unilateral Change, Photo & Media Rights,
  Confidentiality / NDA, Payment Terms, Limitation of Liability, Warranty Disclaimer
- "raw_text": EXACT verbatim text from the document (never paraphrase or shorten)
- "location": where it appears e.g. "Section 3", "Article IV", "Paragraph 2"

Rules:
- Extract ALL instances. Be thorough.
- If a clause type appears multiple times, extract each one separately.
- No explanation, no markdown fences. Raw JSON array only.

Document: {document_name} ({document_type})
--- START ---
{document_text}
--- END ---"""


async def run_extractor(
    document_text: str,
    document_name: str,
    document_type: str,
    thread_id: str,
) -> List[Dict[str, Any]]:
    print("Agent 1 (Extractor): Finding clauses...")
    canadian_law = await backboard_get_global_law_context(thread_id)
    prompt = EXTRACTOR_PROMPT.format(
        canadian_law=canadian_law,
        document_name=document_name,
        document_type=document_type,
        document_text=document_text[:50000],
    )
    try:
        raw = await call_llm(extractor_llm(), prompt)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        clauses = [
            {
                "id": c["id"],
                "type": c["type"],
                "raw_text": c["raw_text"],
                "location": c["location"],
            }
            for c in json.loads(raw)
            if all(k in c for k in ["id", "type", "raw_text", "location"])
        ]
        print(f"  -> Found {len(clauses)} clauses")
        await backboard_save(
            thread_id,
            "assistant",
            f"EXTRACTOR: Found {len(clauses)} clauses.\n{json.dumps(clauses)}",
        )
        return clauses
    except Exception as e:
        print(f"  -> Extractor error: {e}")
        return []

