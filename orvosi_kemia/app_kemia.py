from __future__ import annotations
import csv
import json
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import streamlit as st


# =========================================================
# Alapbeállítások
# =========================================================

APP_DIR = Path(__file__).parent
KERDES_SZAM_KOR = 10
KUSZOB = 7


# =========================================================
# 1) Kérdés + válasz feldolgozása
# =========================================================


def split_question_answer(q_text: str, a_text: str) -> Tuple[str, List[str]]:
    """
    A válasz a 'answer' oszlopban van.
    A válaszon belül a ';' = külön sor.
    """
    q = (q_text or "").strip()
    a = (a_text or "").strip()
    if not q:
        return "", [""]

    if not a:
        return q, [""]

    parts = [p.strip() for p in a.split(";") if p.strip() != ""]
    return q, (parts or [""])


# =========================================================
# 2) Sorszám kinyerése (1.1., 2.3., 1.100. → 1.01 / 2.03 / 1.100)
# =========================================================


def extract_qnum(kerdes: str) -> str | None:
    """
    CSV formák:
      1.
      1.1.
      1.10.
      1.100.
      2.3.
      2.10.
    Kimenet:
      1.01, 1.10, 1.100, 2.03, stb.
    """
    s = unicodedata.normalize("NFKC", kerdes or "").strip()
    m = re.match(r"^(\d+)\.(\d+)\.", s)
    if not m:
        return None

    felev = m.group(1)
    sub = m.group(2)

    if len(sub) == 1:
        sub = "0" + sub

    return f"{felev}.{sub}"


# =========================================================
# 3) Képfájlok keresése — PNG + aláhúzás (_)
# =========================================================


def find_images(qnum: str, pic_dir: Path) -> List[Path]:
    """
    Szigorú képszabály:
      • fő kép:       qnum.png / qnum.PNG
      • extra képek:  qnum_*.png / qnum_*.PNG
    JPG/JPEG nem engedélyezett → nem lesz duplikáció.
    """
    images: List[Path] = []

    # Fő kép
    for ext in (".png", ".PNG"):
        p = pic_dir / f"{qnum}{ext}"
        if p.exists():
            images.append(p)
            break  # csak egy fő kép legyen

    # Extra képek (_ után)
    extras = []
    for ext in (".png", ".PNG"):
        extras.extend(
            sorted(pic_dir.glob(f"{qnum}_*{ext}"), key=lambda p: p.name.lower())
        )

    # Dedup
    out, seen = [], set()
    for p in images + extras:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)

    return out


# =========================================================
# 4) CSV beolvasása
# =========================================================


def read_csv_intelligent(path: Path) -> Dict[str, List[str]]:
    qa: Dict[str, List[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}

        fn = {c.lower().strip(): c for c in reader.fieldnames}
        c_q = fn.get("question")
        c_a = fn.get("answer")

        for row in reader:
            q_text = (row.get(c_q) or "").strip()
            a_text = (row.get(c_a) or "").strip()
            q, answers = split_question_answer(q_text, a_text)
            if q:
                qa[q] = answers

    return qa


# =========================================================
# 5) Kérdések kiválasztása
# =========================================================


def valassz_kerdese(qa: Dict[str, List[str]], db: int) -> List[str]:
    keys = list(qa.keys())
    if len(keys) <= db:
        random.shuffle(keys)
        return keys
    return random.sample(keys, db)


# =========================================================
# 6) Cache
# =========================================================


@st.cache_data(show_spinner=False)
def betolt_qa_cached(path: Path) -> Dict[str, List[str]]:
    return read_csv_intelligent(path)


# =========================================================
# 7) App fő logikája
# =========================================================


def run_app():
    st.set_page_config(page_title="Orvosi kémia kvíz", page_icon="🧪", layout="wide")

    # Félévválasztó
    felev = st.selectbox("Félév kiválasztása", ["1. félév", "2. félév"], index=0)

    # Cím
    st.title("🧪 Orvosi Kémia – Minimumkövetelmény kvíz (önértékelős)")

    # Források
    if felev == "1. félév":
        CSV_PATH = APP_DIR / "kerdes_valaszok_kemia1.csv"
        PIC_DIR = APP_DIR / "pic1"
    else:
        CSV_PATH = APP_DIR / "kerdes_valaszok_kemia2.csv"
        PIC_DIR = APP_DIR / "pic2"

    qa = betolt_qa_cached(CSV_PATH)

    # Session state
    ss = st.session_state
    ss.setdefault("kor_kerdesei", [])
    ss.setdefault("show_answer", {})
    ss.setdefault("itel", {})
    ss.setdefault("osszegzes", None)

    # Gombok
    col1, col2 = st.columns(2)
    with col1:
        st.button(
            f"🧪 Új kör indítása ({KERDES_SZAM_KOR} kérdés)",
            type="primary",
            use_container_width=True,
            on_click=lambda: start_new_round(qa),
        )
    with col2:
        st.button("♻️ Teljes reset", use_container_width=True, on_click=reset_all)

    st.divider()

    if not ss.kor_kerdesei:
        st.info("Kezdéshez indíts új kört.")
        return

    # Állapot
    helyes_db = sum(1 for k in ss.kor_kerdesei if ss.itel.get(k) == "helyes")
    itelt_db = sum(1 for k in ss.kor_kerdesei if ss.itel.get(k) in ("helyes", "hibas"))

    st.caption(f"Önértékelt: {itelt_db}/{len(ss.kor_kerdesei)} — Helyes: {helyes_db}")

    # Kérdések
    for i, kerdes in enumerate(ss.kor_kerdesei, start=1):
        st.markdown(f"**{i}.** {kerdes}")
        cA, cB = st.columns([1, 2])

        with cA:
            st.button(
                "👀 Válasz megjelenítése",
                key=f"show_{i}",
                use_container_width=True,
                on_click=lambda k=kerdes: ss.show_answer.__setitem__(k, True),
            )

        with cB:
            if ss.show_answer.get(kerdes):

                # válaszok lista
                answers = qa.get(kerdes, [""])
                for a in answers:
                    st.markdown(f"- {a}")

                # képek → nagy, eredeti szerű megjelenítés (NINCS caption)
                qnum = extract_qnum(kerdes)
                if qnum:
                    imgs = find_images(qnum, PIC_DIR)
                    shown = set()
                    for img in imgs:
                        rp = img.resolve()
                        if rp in shown:
                            continue
                        shown.add(rp)

                        # ÚJ: nincs caption, nincs kicsinyítés
                        st.image(str(img), use_container_width=True)

                # önértékelés
                cur = ss.itel.get(kerdes)
                idx = 0 if cur in (None, "helyes") else 1
                val = st.radio(
                    "Önértékelés:",
                    ["Helyesnek ítélem", "Nem volt helyes"],
                    index=idx,
                    key=f"eval_{i}",
                    horizontal=True,
                )
                ss.itel[kerdes] = "helyes" if val == "Helyesnek ítélem" else "hibas"

            else:
                st.info("Kattints a válasz megjelenítésére.")

        st.write("---")

    # Kiértékelés
    if st.button("🏁 Teszt kiértékelése", type="primary"):
        helyes_db = sum(1 for k in ss.kor_kerdesei if ss.itel.get(k) == "helyes")
        ss.osszegzes = {"helyes_db": helyes_db, "sikeres": helyes_db >= KUSZOB}

    if ss.osszegzes:
        h = ss.osszegzes["helyes_db"]
        s = ss.osszegzes["sikeres"]

        if s:
            st.success(f"✅ Sikeres — {h}/{len(ss.kor_kerdesei)}")
        else:
            st.error(f"❌ Sikertelen — {h}/{len(ss.kor_kerdesei)}")

        export = {
            "kor_id": datetime.utcnow().isoformat() + "Z",
            "kerdesek_szama": len(ss.kor_kerdesei),
            "kuszob": KUSZOB,
            "helyes_db": h,
            "sikeres": s,
            "reszletek": [
                {"kerdes": k, "valaszok": qa.get(k, [""]), "itel": ss.itel.get(k)}
                for k in ss.kor_kerdesei
            ],
        }

        st.download_button(
            "📥 JSON export",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="kviz_eredmeny.json",
            mime="application/json",
        )


# =========================================================
# Segédfüggvények
# =========================================================


def start_new_round(qa: Dict[str, List[str]]):
    ss = st.session_state
    ss.kor_kerdesei = valassz_kerdese(qa, KERDES_SZAM_KOR)
    ss.show_answer = {k: False for k in ss.kor_kerdesei}
    ss.itel = {k: None for k in ss.kor_kerdesei}
    ss.osszegzes = None


def reset_all():
    ss = st.session_state
    ss.kor_kerdesei = []
    ss.show_answer = {}
    ss.itel = {}
    ss.osszegzes = None


# =========================================================
# Futtatás
# =========================================================

if __name__ == "__main__":
    run_app()
