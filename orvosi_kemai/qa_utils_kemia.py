from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List


QUESTION_HEADER_RE = re.compile(r"(?m)^\s*(\d+)\.\s*(.*?)!\s*$")
# Példa: "1. Definiálja az izotópok fogalmát!"  -- a 2. csoport lesz a kérdés szövege.


def _parse_answers_block(block: str) -> List[str]:
    """
    A válaszblokkot bulletok szerint (sor eleji '-' jel) feldarabolja.
    Minden bullethoz tartozó többsoros tartalmat egy elemként ad vissza.

    - A bullet sor mintája: ^\\s*-\\s+(.*)
    - A következő bulletig (vagy a blokk végéig) tartozó sorok a bullethoz kerülnek.
    - Üres és whitespace-only sorok megtarthatók a formázás miatt (ASCII rajzoknál hasznos).

    Ha a blokkban nincs bullet, de van tartalom, a teljes blokk egy elemként kerül vissza.
    """
    lines = block.splitlines()
    answers: List[str] = []

    current: List[str] = []
    in_bullet = False

    for ln in lines:
        m = re.match(r"^\s*-\s+(.*)", ln)
        if m:
            # új bullet kezdődik
            # ha volt előző bullet, zárjuk le és mentsük
            if current:
                # trimmelés jobb/bal oldalon, de a belső sortöréseket meghagyjuk
                answers.append("\n".join(current).strip())
                current = []
            in_bullet = True
            # bullet első sora: a minta utáni rész
            current.append(m.group(1))
        else:
            # nem bullet sor
            if in_bullet:
                # az aktuális bullet folytatása (pl. ASCII rajz, magyarázat)
                current.append(ln.rstrip())
            else:
                # bullet előtt lévő "zaj": kihagyjuk (pl. üres sorok),
                # vagy később a teljes blokkot egy elemként adjuk vissza
                pass

    # lezárás: utolsó bullet mentése
    if current:
        answers.append("\n".join(current).strip())

    # ha nem találtunk bulletot, de a blokk nem üres, adjuk vissza egy elemben
    raw = block.strip()
    if not answers and raw:
        answers.append(raw)

    # töröljük az üres elemeket
    answers = [a for a in answers if a.strip()]
    return answers


def beolvas_csv_dict(filename: str) -> Dict[str, List[str]]:
    """
    Beolvasás a következő formátumból:

        1. Kérdés szövege ... !
        - válasz 1
        - válasz 2 (többsoros is lehet)
        2. Következő kérdés ... !
        - válasz ...

    A "kérdés" a sorszámtól a '!'-ig tart, a válaszok pedig az ezt követő blokk
    a következő számozott kérdés kezdetéig.

    Visszatér: { kérdés: [válasz1, válasz2, ...] }

    Megjegyzés: BOM-toleráns (utf-8-sig).
    """
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Nem található a fájl: {path.resolve()}")

    text: str
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()

    # Keressük meg az összes számozott kérdés fejléct (pozíciókkal együtt)
    matches = list(QUESTION_HEADER_RE.finditer(text))
    if not matches:
        raise ValueError(
            "Nem található számozott kérdés fejléc a fájlban. "
            "Elvárt minta pl.: '1. Kérdés ... !'"
        )

    qa: Dict[str, List[str]] = {}

    for i, m in enumerate(matches):
        # Kérdés szövege a 2. csoport
        question = m.group(2).strip()
        # A válaszblokk a header vége és a következő header eleje közötti rész
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        answers = _parse_answers_block(block)
        qa[question] = answers

    return qa


def valassz_kerdeseket(qa: Dict[str, List[str]], n: int = 12) -> List[str]:
    """
    Véletlenszerűen kiválaszt n egyedi kérdést.
    """
    import random

    if n > len(qa):
        raise ValueError(
            "Nagyobb számot adtál meg, mint ahány kérdés rendelkezésre áll."
        )
    return random.sample(list(qa.keys()), n)
