from __future__ import annotations
import csv
import json
import random
import re
from datetime import datetime
from pathlib import Path
import streamlit as st


# ─────────────────────────────────────────────────────────
# Alapbeállítások
APP_DIR = Path(__file__).parent
KERDES_SZAM_KOR = 10
KUSZOB = 7


# ─────────────────────────────────────────────────────────
# CSV beolvasás (question / answer)
def beolvas_csv(path: Path) -> dict[str, list[str]]:
    """
    Beolvassa a CSV-t. Elvárt oszlopok: question, answer.
    Ha a válasz nincs külön oszlopban, az első ? vagy ! után levágjuk (a maradék lesz a válasz).
    A válaszokat ';' és sortörés alapján daraboljuk sorokra.
    Ha nincs válasz, egyetlen üres sort adunk vissza.
    """
    qa: dict[str, list[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}

        fn = {c.lower().strip(): c for c in reader.fieldnames}
        c_q = fn.get("question") or fn.get("kerdes") or fn.get("kérdés")
        c_a = fn.get("answer") or fn.get("valasz") or fn.get("válasz")

        for row in reader:
            q_raw = (row.get(c_q) or "").strip() if c_q else ""
            a_raw = (row.get(c_a) or "").strip() if c_a else ""

            # Ha egy cellában van a kérdés+válasz → split ? vagy ! után
            if not a_raw and q_raw:
                parts = re.split(r"([!?])", q_raw, maxsplit=1)
                if len(parts) >= 3:
                    q_raw = (parts[0] + parts[1]).strip()
                    a_raw = parts[2].strip()

            if not q_raw:
                continue

            if a_raw:
                parts = re.split(r";|\n", a_raw)
                answers = [p.strip() for p in parts if p.strip() != ""]
                if not answers:
                    answers = [""]  # üres sor
            else:
                answers = [""]  # üres sor, ha nincs válasz

            qa[q_raw] = answers

    return qa


# ─────────────────────────────────────────────────────────
# Képek és kérdés-sorszám kinyerése
def extract_qnum(kerdes: str) -> str | None:
    """
    A kérdés elejéről kiveszi az x.xx formátumot (pl. 1.01 vagy 2.09).
    Csak a legelején lévő minta számít.
    """
    m = re.match(r"^\s*(\d+\.\d{2})", kerdes)
    return m.group(1) if m else None


def find_images(qnum: str, pic_dir: Path) -> list[Path]:
    """
    Képkeresés a következő minták szerint (kis/nagy kiterjesztés is):
      - x.xx.png / x.xx.PNG
      - x.xx_*.png / x.xx_*.PNG
    """
    exts = (".png", ".PNG")
    images: list[Path] = []

    # Fő kép
    for ext in exts:
        p = pic_dir / f"{qnum}{ext}"
        if p.exists():
            images.append(p)

    # Több kép: x.xx_*.png
    for ext in exts:
        images.extend(sorted(pic_dir.glob(f"{qnum}_*{ext}"), key=lambda p: p.name))

    # Dedup
    out, seen = [], set()
    for p in images:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


# ─────────────────────────────────────────────────────────
# Kérdésválasztás
def valassz_kerdeseket(qa: dict[str, list[str]], db: int) -> list[str]:
    keys = list(qa.keys())
    if len(keys) <= db:
        random.shuffle(keys)
        return keys
    return random.sample(keys, db)


# ─────────────────────────────────────────────────────────
# Cache
@st.cache_data(show_spinner=False)
def betolt_qa_cached(path: Path) -> dict[str, list[str]]:
    return beolvas_csv(path)


# ─────────────────────────────────────────────────────────
# App
def run_app():
    st.set_page_config(page_title="Orvosi kémia kvíz", page_icon="🧪", layout="wide")

    # ─── Félévválasztó a cím ELÉ (nincs oldalsáv) ────────
    felev = st.selectbox("Félév kiválasztása", ["1. félév", "2. félév"], index=0)

    # Cím a félévválasztó alatt
    st.title("🧪 Orvosi Kémia – Minimumkövetelmény kvíz (önértékelős)")

    # Félévhez tartozó források (nincs oldalsávos ellenőrzés)
    if felev == "1. félév":
        CSV_PATH = APP_DIR / "kerdes_valaszok_kemia1.csv"
        PIC_DIR = APP_DIR / "pic1"
    else:
        CSV_PATH = APP_DIR / "kerdes_valaszok_kemia2.csv"
        PIC_DIR = APP_DIR / "pic2"

    # CSV betöltés (egyszerűen, ellenőrzés nélkül)
    qa = betolt_qa_cached(CSV_PATH)

    # ─── Session state ────────────────────────────────────
    if "kor_kerdesei" not in st.session_state:
        st.session_state.kor_kerdesei = []
    if "show_answer" not in st.session_state:
        st.session_state.show_answer = {}
    if "itel" not in st.session_state:
        st.session_state.itel = {}
    if "osszegzes" not in st.session_state:
        st.session_state.osszegzes = None

    # ─── Funkciók ─────────────────────────────────────────
    def uj_kor():
        st.session_state.kor_kerdesei = valassz_kerdeseket(qa, KERDES_SZAM_KOR)
        st.session_state.show_answer = {k: False for k in st.session_state.kor_kerdesei}
        st.session_state.itel = {k: None for k in st.session_state.kor_kerdesei}
        st.session_state.osszegzes = None

    def reset_minden():
        st.session_state.kor_kerdesei = []
        st.session_state.show_answer = {}
        st.session_state.itel = {}
        st.session_state.osszegzes = None

    # ─── Felső gombok ─────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.button(
            f"🧪 Új kör indítása ({KERDES_SZAM_KOR} kérdés)",
            type="primary",
            use_container_width=True,
            on_click=uj_kor,
        )
    with c2:
        st.button("♻️ Teljes reset", use_container_width=True, on_click=reset_minden)

    st.divider()

    # Ha nincs aktív kör
    if not st.session_state.kor_kerdesei:
        st.info(
            f"Kezdéshez kattints az **Új kör indítása ({KERDES_SZAM_KOR} kérdés)** gombra!"
        )
        return

    # ─── Kérdések listázása ──────────────────────────────
    helyes_db = sum(
        1
        for k in st.session_state.kor_kerdesei
        if st.session_state.itel.get(k) == "helyes"
    )
    itelt_db = sum(
        1
        for k in st.session_state.kor_kerdesei
        if st.session_state.itel.get(k) in ("helyes", "hibas")
    )

    st.caption(
        f"Önértékelt kérdések: {itelt_db} / {len(st.session_state.kor_kerdesei)} "
        f"— Helyesnek ítélt: {helyes_db}"
    )

    for i, kerdes in enumerate(st.session_state.kor_kerdesei, start=1):
        st.markdown(f"**{i}.** {kerdes}")
        col1, col2 = st.columns([1, 2])

        with col1:
            st.button(
                "👀 Válasz megjelenítése",
                key=f"show_{i}",
                use_container_width=True,
                on_click=lambda k=kerdes: st.session_state.show_answer.__setitem__(
                    k, True
                ),
            )

        with col2:
            if st.session_state.show_answer.get(kerdes):
                st.success("Elfogadható válasz(ok):")
                answers = qa.get(kerdes, [""])
                if not answers:
                    answers = [""]  # üres sor
                st.markdown("\n".join(answers))

                # Képek (x.xx.png és x.xx_*.png kis/NAGY kiterjesztéssel)
                qnum = extract_qnum(kerdes)
                if qnum:
                    imgs = find_images(qnum, PIC_DIR)
                    for idx, img in enumerate(imgs, start=1):
                        st.image(
                            str(img),
                            caption=f"{qnum} ({idx})",
                            use_container_width=True,
                        )

                # Önértékelés
                cur = st.session_state.itel.get(kerdes)
                default_index = 0 if cur in (None, "helyes") else 1
                val = st.radio(
                    "Önértékelés:",
                    ["Helyesnek ítélem", "Nem volt helyes"],
                    index=default_index,
                    key=f"radio_{i}",
                    horizontal=True,
                )
                st.session_state.itel[kerdes] = (
                    "helyes" if val == "Helyesnek ítélem" else "hibas"
                )
            else:
                st.info("Kattints a „Válasz megjelenítése” gombra.")

        st.write("---")

    # ─── Kiértékelés ─────────────────────────────────────
    if st.button("🏁 Teszt kiértékelése", type="primary"):
        helyes_db = sum(
            1
            for k in st.session_state.kor_kerdesei
            if st.session_state.itel.get(k) == "helyes"
        )
        sikeres = helyes_db >= KUSZOB
        st.session_state.osszegzes = {"helyes_db": helyes_db, "sikeres": sikeres}

    if st.session_state.osszegzes:
        h = st.session_state.osszegzes["helyes_db"]
        s = st.session_state.osszegzes["sikeres"]

        if s:
            st.success(f"✅ Sikeres teszt! {h} / {len(st.session_state.kor_kerdesei)}")
        else:
            st.error(f"❌ Sikertelen teszt. {h} / {len(st.session_state.kor_kerdesei)}")

        export = {
            "kor_id": datetime.utcnow().isoformat() + "Z",
            "kerdesek_szama": len(st.session_state.kor_kerdesei),
            "kuszob": KUSZOB,
            "helyes_db": h,
            "sikeres": s,
            "reszletek": [
                {
                    "kerdes": k,
                    "valaszok": qa.get(k, [""]) or [""],
                    "itel": st.session_state.itel.get(k),
                }
                for k in st.session_state.kor_kerdesei
            ],
        }

        st.download_button(
            label="📥 Eredmények letöltése (JSON)",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="kviz_eredmeny.json",
            mime="application/json",
        )


if __name__ == "__main__":
    run_app()
