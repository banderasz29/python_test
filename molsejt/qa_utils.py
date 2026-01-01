import csv
from typing import Dict, List
from pathlib import Path


def _split_answers(ans_text: str) -> List[str]:
    """
    Válaszok bontása rugalmas szeparátorokkal.
    Preferált: '|', ha az nincs, próbál ';', végül ','.
    Visszatér: tisztított, nem üres válaszok listája.
    """
    s = (ans_text or "").strip()
    if not s:
        return []
    # Elsődleges szeparátor
    if "|" in s:
        parts = s.split("|")
    elif ";" in s:
        parts = s.split(";")
    elif "," in s:
        parts = s.split(",")
    else:
        parts = [s]
    return [p.strip() for p in parts if p.strip()]


def beolvas_csv_dict(filename: str) -> Dict[str, List[str]]:
    """
    CSV beolvasás olyan állományokhoz, ahol MINDEN sor egyetlen 'kérdés + válaszok' szöveget tartalmaz,
    és a KÉRDÉS a legelső '?' karakterig tart, a válaszok pedig utána következnek.

    - BOM-toleráns (utf-8-sig).
    - Delimiter-agnosztikus: működik akkor is, ha több oszlop van (pl. , ; TAB),
      mert a sor celláit összefűzzük egy teljes szöveggé ' ' közökkel.
    - A válaszokat rugalmasan '|' majd ';' végül ',' szeparátorokkal próbálja bontani.
    - Üres sorokat és '?' nélküli sorokat kihagy (vagy opcionálisan hibát dobhatnánk).

    Visszatérés:
      { kérdés: [elfogadható_válaszok, ...], ... }
    """
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Nem található a CSV: {path.resolve()}")

    # 1) Olvasás és delimiter detektálás
    with open(path, mode="r", encoding="utf-8-sig", newline="") as f:
        try:
            sample = f.read(4096)
        finally:
            f.seek(0)

        # Próbáljuk felismerni a delimiter(eke)t, de mivel a sor teljes szövegét fogjuk használni,
        # itt a pontos delimiter kevésbé kritikus; a cél az, hogy szétesse a sorokat.
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        except csv.Error:
            # Ha nem megy a sniff, essünk vissza egyszerű csv-re (vessző)
            dialect = csv.excel

        reader = csv.reader(f, dialect)
        rows = list(reader)

    data: Dict[str, List[str]] = {}
    empty_count = 0
    skipped_no_qmark = 0

    for row in rows:
        # üres sor?
        if not row or all((c or "").strip() == "" for c in row):
            empty_count += 1
            continue

        # Fűzzük össze a cellákat egyetlen szöveggé (néha az egész sor az első cellában van, néha nem)
        full_text = " ".join((c or "").strip() for c in row).strip()
        if not full_text:
            empty_count += 1
            continue

        # Keressük az első kérdőjelet
        qmark_pos = full_text.find("?")
        if qmark_pos == -1:
            # nincs kérdőjel → nem tudjuk szétválasztani kérdés/válaszok részt → kihagyjuk
            skipped_no_qmark += 1
            continue

        # Kérdés: a kérdőjelig BELEÉRTVE a '?'-t (tisztítva)
        question = (full_text[: qmark_pos + 1]).strip()
        # Válaszok: a kérdőjel utáni rész
        answers_text = (full_text[qmark_pos + 1 :]).strip()
        answers = _split_answers(answers_text)

        if not question:
            # elméletileg nem fordulhat elő, de biztos ami biztos
            continue

        data[question] = answers

    if not data:
        # Segítő hibaüzenet – elmondja, mennyit és miért hagytunk ki
        raise ValueError(
            "Nem sikerült kérdés–válasz párokat beolvasni a CSV-ből. "
            f"Kihagyott üres sorok: {empty_count}, '?' nélküli sorok: {skipped_no_qmark}. "
            "Ellenőrizd, hogy minden sor tartalmaz-e kérdőjelet, és a válaszok a '?' után szerepelnek!"
        )

    return data


def valassz_kerdeseket(qa: Dict[str, List[str]], n: int = 12) -> List[str]:
    import random

    if n > len(qa):
        raise ValueError(
            "Nagyobb számot adtál meg, mint ahány kérdés rendelkezésre áll."
        )
    return random.sample(list(qa.keys()), n)
