from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from qa_utils import beolvas_csv_dict

APP_DIR = Path(__file__).parent.resolve()
PDF_TEXT = APP_DIR / "sources" / "szeberenyi_molekularis_sejtbiologia.txt"
OUTPUT = APP_DIR / "answer_explanations.json"

STOPWORDS = {
    "a", "az", "egy", "és", "vagy", "hogy", "mely", "milyen", "sorolja", "fel", "nevezzen",
    "meg", "között", "közül", "esetén", "használatakor", "szempontjából", "mi", "mit", "hol",
    "hogyan", "kettő", "három", "2", "3", "fő", "van", "vannak", "illetve", "amely", "amelyek",
    "nem", "is", "lehet", "kell", "sejt", "sejtek", "rendszer", "folyamat", "funkció", "részt",
    "szerkezet", "szerkezete", "szerkezetét", "különbség", "különbsége", "típus", "típusa",
    "rózsaszín", "piros", "kék", "lila", "zöld", "sárga", "fehér", "fekete",
}

GENERIC_ANSWER_TERMS = {"rozsaszin", "piros", "kek", "lila", "zold", "sarga", "feher", "fekete", "igen", "nem"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i")
    return re.sub(r"\s+", " ", text).strip()


def is_useful_sentence(sentence: str) -> bool:
    stripped = sentence.strip()
    if not (40 <= len(stripped) <= 420):
        return False
    if "....." in stripped or stripped.count(".") > 12:
        return False
    if re.search(r"\.{3,}\s*\d+", stripped):
        return False
    lowered = stripped.lower()
    if lowered.startswith(("ábra", "táblázat", "fejezet")):
        return False
    if "created by xmlmind" in lowered or "xmlmind xsl-fo" in lowered:
        return False
    if re.search(r"\b\d+\.\d+\.\s*ábra\s*-", lowered):
        return False
    letters = sum(ch.isalpha() for ch in stripped)
    return letters / max(len(stripped), 1) > 0.45


def split_sentences(text: str) -> List[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÖŐÚÜŰ0-9])", text)
    return [p.strip() for p in parts if is_useful_sentence(p)]


def answer_terms(answers: List[str]) -> List[str]:
    raw = " ; ".join(answers)
    raw = re.sub(r"\([^)]*\)", " ", raw)
    raw = raw.replace("/", ";").replace(" - ", ";")
    candidates = []
    for part in re.split(r"[;,:\n]", raw):
        part = re.sub(r"\s+", " ", part).strip(" .;:-")
        if not part or len(part) < 4:
            continue
        norm = normalize(part)
        if norm in STOPWORDS:
            continue
        candidates.append(part)
    # Ha kevés a jó jelölt, a válasz fontosabb szavait is felvesszük.
    words = re.findall(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9\-]{5,}", raw)
    for word in words:
        if normalize(word) not in STOPWORDS:
            candidates.append(word)
    seen = set()
    uniq: List[str] = []
    for cand in candidates:
        key = normalize(cand)
        if key and key not in seen:
            seen.add(key)
            uniq.append(cand)
    return uniq[:8]


def question_terms(question: str) -> List[str]:
    terms = []
    for word in re.findall(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9\-]{5,}", question):
        key = normalize(word)
        if key not in STOPWORDS:
            terms.append(word)
    return terms[:6]


def score_sentence(sentence_norm: str, terms_norm: List[str], q_terms_norm: List[str]) -> int:
    score = 0
    answer_hits = 0
    question_hits = 0
    generic_only = terms_norm and all(term in GENERIC_ANSWER_TERMS for term in terms_norm)
    for term in terms_norm:
        if term and term in sentence_norm:
            answer_hits += 1
            score += 5 + min(len(term), 20) // 4
    for term in q_terms_norm:
        if term and term in sentence_norm:
            question_hits += 1
            score += 2
    if answer_hits == 0:
        return 0
    if generic_only and question_hits == 0:
        return 0
    return score


def concise_join(sentences: Iterable[str], max_chars: int = 520) -> str:
    result: List[str] = []
    total = 0
    seen = set()
    for sentence in sentences:
        sentence = re.sub(r"\s+", " ", sentence).strip()
        key = normalize(sentence[:120])
        if key in seen:
            continue
        seen.add(key)
        if total + len(sentence) + 1 > max_chars and result:
            break
        result.append(sentence)
        total += len(sentence) + 1
        if len(result) >= 3:
            break
    return " ".join(result).strip()


def fallback_explanation(answers: List[str], question: str) -> str:
    terms = answer_terms(answers)
    if terms:
        joined = ", ".join(terms[:4])
        return f"{joined}: a megadott válaszhoz tartozó fogalom vagy fogalomcsoport. A kérdés kontextusában ezek határozzák meg a kért struktúrát, példát, helyet vagy funkciót."
    return "Ehhez a válaszhoz nem található külön, rövid forrásmagyarázat az előkészített tananyag-kivonatban."


def build_explanation(question: str, answers: List[str], sentences: List[str], sentence_norms: List[str]) -> str:
    terms = answer_terms(answers)
    q_terms = question_terms(question)
    terms_norm = [normalize(t) for t in terms if len(normalize(t)) >= 4]
    q_terms_norm = [normalize(t) for t in q_terms if len(normalize(t)) >= 5]

    scored: List[Tuple[int, int, str]] = []
    for idx, sentence_norm in enumerate(sentence_norms):
        score = score_sentence(sentence_norm, terms_norm, q_terms_norm)
        if score > 0:
            scored.append((score, idx, sentences[idx]))
    scored.sort(key=lambda x: (-x[0], x[1]))

    best_score = scored[0][0] if scored else 0
    explanation = concise_join(sentence for _, _, sentence in scored[:8])
    if explanation and best_score >= 6:
        return explanation
    return fallback_explanation(answers, question)


def load_all_questions() -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for filename in ["kerdes_valaszok.csv", "kerdes_valaszok2.csv"]:
        qa = beolvas_csv_dict(str(APP_DIR / filename))
        for question, answers in qa.items():
            if question not in merged:
                merged[question] = answers
            else:
                seen = {normalize(a) for a in merged[question]}
                for answer in answers:
                    key = normalize(answer)
                    if key and key not in seen:
                        merged[question].append(answer)
                        seen.add(key)
    return merged


def main() -> None:
    if not PDF_TEXT.exists():
        raise FileNotFoundError(f"Hiányzik a kinyert PDF-szöveg: {PDF_TEXT}")
    text = PDF_TEXT.read_text(encoding="utf-8", errors="ignore")
    sentences = split_sentences(text)
    sentence_norms = [normalize(sentence) for sentence in sentences]
    qa = load_all_questions()
    explanations = {
        question: build_explanation(question, answers, sentences, sentence_norms)
        for question, answers in qa.items()
    }
    OUTPUT.write_text(json.dumps(explanations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kérdések: {len(qa)}")
    print(f"Mondatok a PDF-ből: {len(sentences)}")
    print(f"Magyarázatfájl: {OUTPUT}")


if __name__ == "__main__":
    main()
