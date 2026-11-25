"""
Markdown Documentation Generator for SmartDesk AI.
Reads canonical knowledge base and deliberate gap datasets from JSON files
and generates formatted Markdown documentation organized by domain.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
KB_DIR = BASE_DIR / "data" / "knowledge_base"
MD_DIR = KB_DIR / "markdown"
JSON_ENTRIES_FILE = KB_DIR / "kb_entries.json"
JSON_GAPS_FILE = KB_DIR / "deliberate_gaps.json"


def load_json(filepath: Path) -> List[Dict[str, Any]]:
    """Load and validate JSON dataset."""
    if not filepath.exists():
        raise FileNotFoundError(f"Required JSON file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Loaded {len(data)} items from {filepath.name}")
    return data


def generate_markdown_docs():
    """Reads kb_entries.json and generates structured Markdown files by domain."""
    entries = load_json(JSON_ENTRIES_FILE)
    gaps = load_json(JSON_GAPS_FILE)

    MD_DIR.mkdir(parents=True, exist_ok=True)
    generated_count = 0

    for entry in entries:
        # Validate mandatory schema fields
        for field in ("id", "domain", "category", "title", "content"):
            if field not in entry:
                raise ValueError(f"Entry {entry.get('id', 'UNKNOWN')} missing mandatory field '{field}'")

        domain_slug = entry["domain"].lower().replace(" ", "_").replace("&", "and")
        domain_dir = MD_DIR / domain_slug
        domain_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{entry['id'].lower()}_{entry['title'].lower().replace(' ', '_').replace('/', '_')[:40]}.md"
        filepath = domain_dir / filename

        keywords_str = ", ".join(entry.get("keywords", []))
        sample_questions_md = "\n".join(f"- *{q}*" for q in entry.get("sample_questions", []))

        md_content = f"""# {entry['title']}

- **Document ID**: `{entry['id']}`
- **Domain**: {entry['domain']}
- **Category**: {entry['category']}
- **Keywords**: {keywords_str}

## Policy & Procedure Details
{entry['content']}

## Frequently Asked Questions
{sample_questions_md}
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        generated_count += 1

    logger.info(f"Successfully generated {generated_count} Markdown policy files in {MD_DIR}")
    logger.info(f"Verified {len(gaps)} deliberate gap scenarios in {JSON_GAPS_FILE.name}")


if __name__ == "__main__":
    generate_markdown_docs()
