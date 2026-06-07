from __future__ import annotations

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
JSON_PATH = APP_DIR / "answer_explanations.json"


def remove_figure_references(text: str) -> str:
    """Eltávolítja az ábrahivatkozásokat, például: (5.4. ábra), 8.6.A. ábra, 8.6. ábra: ..."""
    cleaned = text
    # Zárójeles hivatkozások: (5.4. ábra), (8.6.A. ábra), (l. 15.2. ábra)
    cleaned = re.sub(
        r"\s*\([^)]*\b\d+(?:\.\d+)*(?:\.[A-Z])?\.\s*ábra\b[^)]*\)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Egyszerű mondatközi hivatkozások: 5.4. ábra, 8.6.A. ábra
    cleaned = re.sub(
        r"\s*\b\d+(?:\.\d+)*(?:\.[A-Z])?\.\s*ábra\b\s*:?,?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Ritkább forma: 14.2.ábra
    cleaned = re.sub(
        r"\s*\b\d+(?:\.\d+)*(?:\.[A-Z])?\.\s*ábra\b\s*:?,?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    cleaned = {question: remove_figure_references(explanation) for question, explanation in data.items()}
    JSON_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = sum(1 for key in data if data[key] != cleaned[key])
    remaining = sum(1 for value in cleaned.values() if re.search(r"\bábra\b", value, flags=re.IGNORECASE))
    print(f"Tisztított bejegyzések: {changed}")
    print(f"Ábra szóval még rendelkező bejegyzések: {remaining}")


if __name__ == "__main__":
    main()
