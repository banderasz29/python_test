from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import json
import io
import csv
import os
import re
import streamlit as st

# Kérdésválogatás és CSV beolvasás – győződj meg róla, hogy qa_utils.py ugyanebben a mappában van.
from qa_utils import valassz_forras_es_kerdesek

# ─────────────────────────────────────────────────────────
# Mindig az app fájlja MELLŐL dolgozunk, függetlenül a CWD-től
APP_DIR: Path = Path(__file__).parent.resolve()

# Fix paraméterek
THRESHOLD: int = 12  # ennyi kérdés töltődik be minden módban
PASS_MIN: int = 9  # legalább ennyi helyes kell a sikerhez (12-ből 9)
FAJL_1: Path = APP_DIR / "kerdes_valaszok.csv"  # 1. félév
FAJL_2: Path = APP_DIR / "kerdes_valaszok2.csv"  # 2. félév
SEED: Optional[int] = None  # kompatibilitási okból megmaradt; sorrendi módban nincs hatása

st.set_page_config(
    page_title="Molekuláris sejtbiológia – minimum kérdések teszt",
    page_icon="🧬",
    layout="wide",
)

# Oldalsáv – csak vizsgatípus + betöltés
st.sidebar.header("Beállítás")
mod = st.sidebar.selectbox(
    "Vizsga típusa",
    options=["1", "2", "szigorlat"],
    format_func=lambda x: {
        "1": "1. félév",
        "2": "2. félév",
        "szigorlat": "3. szigorlat (50–50%)",
    }[x],
)
start = st.sidebar.button("🎯 Betöltés / újrakezdés")
st.sidebar.caption("A kérdések nem véletlenszerűen, hanem a CSV-fájlok eredeti sorrendjében jelennek meg.")

# Diagnosztika – lásd, honnan fut és mit lát
with st.sidebar.expander("Diagnosztika", expanded=False):
    st.write(f"**CWD**: {os.getcwd()}")
    st.write(f"**__file__**: {__file__}")
    st.write(f"**APP_DIR**: {APP_DIR}")
    st.write(f"**{FAJL_1.name}** exists? {FAJL_1.exists()}")
    st.write(f"**{FAJL_2.name}** exists? {FAJL_2.exists()}")

# Rövid összegzés a fájlokról
st.sidebar.caption(f"📂 Aktív app-könyvtár: `{APP_DIR}`")
st.sidebar.write(
    f"- 1. félév: `{FAJL_1.name}` — **{'OK' if FAJL_1.exists() else 'HIÁNYZIK'}**\n"
    f"- 2. félév: `{FAJL_2.name}` — **{'OK' if FAJL_2.exists() else 'HIÁNYZIK'}**"
)

# ─────────────────────────────────────────────────────────
# Állapot (nincs típusannotáció a session_state-en!)
if "kerdesek" not in st.session_state:
    st.session_state.kerdesek = []  # List[str]
if "qa" not in st.session_state:
    st.session_state.qa = {}  # Dict[str, List[str]]
if "show_answer" not in st.session_state:
    st.session_state.show_answer = {}  # Dict[str, bool]
if "itel" not in st.session_state:
    st.session_state.itel = {}  # Dict[str, Optional[str]]
if "osszegzes" not in st.session_state:
    st.session_state.osszegzes = None  # Optional[Dict[str, object]]
if "source_key" not in st.session_state:
    st.session_state.source_key = None


# ─────────────────────────────────────────────────────────
# Betöltés
MODE_LABELS = {
    "1": "1. félév",
    "2": "2. félév",
    "szigorlat": "3. szigorlat (50–50%)",
}


def current_source_key() -> str:
    """A beállításokból és CSV-időbélyegekből stabil kulcsot képez az automatikus újratöltéshez."""
    fajl_1_mtime = FAJL_1.stat().st_mtime if FAJL_1.exists() else "missing"
    fajl_2_mtime = FAJL_2.stat().st_mtime if FAJL_2.exists() else "missing"
    return f"{mod}|{THRESHOLD}|{fajl_1_mtime}|{fajl_2_mtime}"


def generalj() -> None:
    # Előzetes ellenőrzés – egyértelmű üzenet a hiányzó fájlokra
    missing = []
    if mod in ("1", "szigorlat") and not FAJL_1.exists():
        missing.append(str(FAJL_1))
    if mod in ("2", "szigorlat") and not FAJL_2.exists():
        missing.append(str(FAJL_2))
    if missing:
        st.error(
            "Hiányzó CSV fájl(ok):\n\n- "
            + "\n- ".join(missing)
            + "\n\nTedd a fájl(oka)t az app.py mellé, vagy adj meg másik elérési utat a kódban."
        )
        st.stop()
        return  # extra védelem

    try:
        kerdesek, qa = valassz_forras_es_kerdesek(
            mod=mod, n=THRESHOLD, fajl_1=str(FAJL_1), fajl_2=str(FAJL_2), seed=SEED
        )
    except Exception as e:
        st.error(f"Hiba a kérdések előkészítése során: {e}")
        st.stop()
        return
    else:
        # Csak sikeres beolvasás után állítsunk állapotot
        st.session_state.kerdesek = kerdesek
        st.session_state.qa = qa
        st.session_state.show_answer = {k: False for k in kerdesek}
        st.session_state.itel = {k: None for k in kerdesek}
        st.session_state.osszegzes = None
        st.session_state.source_key = current_source_key()


# Első betöltéskor, gombnyomásra vagy vizsgatípus/CSV-változáskor töltsünk újra
source_key = current_source_key()
if start or not st.session_state.kerdesek or st.session_state.source_key != source_key:
    generalj()

# ─────────────────────────────────────────────────────────
# Fejléc és státusz
st.title("🧬 Molekuláris sejtbiológia – minimum kérdések teszt")
st.caption(
    f"Egyszerre látszik minden kérdés. Mód: **{MODE_LABELS[mod]}** • "
    f"Kérdések száma: **{THRESHOLD}** • Sikeresség feltétele: **legalább {PASS_MIN} helyes**. "
    "A kérdések a forrásfájlok eredeti sorrendjét követik."
)

# Ha valamiért még sincs kérdés (pl. stop után), álljunk meg szépen
if not st.session_state.kerdesek:
    st.info(
        "Nincs betölthető kérdés. Ellenőrizd a CSV fájlokat, majd kattints a Betöltés gombra."
    )
    st.stop()

kerdesek = st.session_state.kerdesek
qa = st.session_state.qa
show_answer = st.session_state.show_answer
itel = st.session_state.itel

itelt_db = sum(1 for k in kerdesek if itel.get(k) in ("helyes", "hibas"))
helyes_db = sum(1 for k in kerdesek if itel.get(k) == "helyes")

c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
with c1:
    st.metric("Kérdések száma", len(kerdesek))
with c2:
    st.metric("Önértékelt", f"{itelt_db}/{len(kerdesek)}")
with c3:
    st.metric("Helyesnek jelölt", helyes_db)
with c4:
    st.button(
        "🔁 Újrakezdés azonos sorrenddel",
        on_click=generalj,
        use_container_width=True,
    )

st.divider()


# ─────────────────────────────────────────────────────────
# Válaszok és rövid magyarázatok formázott megjelenítése
def show_answers_markdown(ans_list: List[str]) -> None:
    if not ans_list:
        st.caption("(Nincs válasz rögzítve)")
        return
    for i, a in enumerate(ans_list, 1):
        text = str(a).strip()
        if "\n" in text:
            st.markdown(f"**{i})**")
            st.code(text)
        else:
            st.markdown(f"**{i})** {text}")


def compact_answer_text(ans_list: List[str]) -> str:
    cleaned = [re.sub(r"\s+", " ", str(a)).strip(" ;") for a in ans_list if str(a).strip()]
    return "; ".join(cleaned)


def short_explanation(question: str, ans_list: List[str]) -> str:
    """Rövid, tanulást segítő magyarázatot készít a rendelkezésre álló válaszokból."""
    cleaned = [re.sub(r"\s+", " ", str(a)).strip(" ;") for a in ans_list if str(a).strip()]
    if not cleaned:
        return "Ehhez a kérdéshez nincs külön magyarázat rögzítve, ezért a tanulásnál a kérdés megfogalmazásából indulj ki."

    if len(cleaned) == 1:
        answer_summary = cleaned[0]
        return (
            f"A válasz lényege: {answer_summary}. Tanuláskor ezt a kulcsállítást kapcsold össze "
            "a kérdésben szereplő fogalommal, mert a minimumkérdések általában a pontos definíciót, "
            "helyet, funkciót vagy fő példát kérik számon."
        )

    answer_summary = "; ".join(cleaned[:3])
    if len(cleaned) > 3:
        answer_summary += "; …"
    return (
        f"A felsorolt elemek a válasz kulcspontjai: {answer_summary}. A kérdés megoldásához elég, ha "
        "a fő fogalmakat és azok kapcsolatát jegyzed meg; több elfogadható válasz esetén ezek gyakran "
        "alternatív példák vagy egymást kiegészítő részletek."
    )


def show_explanation(question: str, ans_list: List[str]) -> None:
    st.markdown("**Rövid magyarázat:**")
    st.info(short_explanation(question, ans_list))


# ─────────────────────────────────────────────────────────
# Kérdésblokkok – „Válasz megjelenítése” + önértékelés
for sorszam, k in enumerate(kerdesek, start=1):
    bg = (
        "#eaffea"
        if itel.get(k) == "helyes"
        else ("#ffecec" if itel.get(k) == "hibas" else "#ffffff")
    )
    st.markdown(
        f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:16px;background:{bg}">
          <div style="font-weight:600;">{sorszam}. kérdés</div>
          <div style="margin-top:6px;">{k}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cA, cB = st.columns([1, 3])
    with cA:
        st.button(
            "👀 Válasz megjelenítése",
            key=f"btn_show_{sorszam}",
            on_click=lambda kk=k: show_answer.__setitem__(kk, True),
            use_container_width=True,
        )
    with cB:
        if show_answer.get(k, False):
            answers = qa.get(k, [])
            st.success("Elfogadható válasz(ok):")
            show_answers_markdown(answers)
            show_explanation(k, answers)

            current = itel.get(k)
            radio_idx = 0 if (current is None or current == "helyes") else 1
            val = st.radio(
                "Önértékelés:",
                options=["Helyesnek ítélem", "Nem volt helyes"],
                index=radio_idx,
                key=f"radio_{sorszam}",
                horizontal=True,
            )
            itel[k] = "helyes" if val == "Helyesnek ítélem" else "hibas"
        else:
            st.info(
                "Kattints a „Válasz megjelenítése” gombra, és utána értékeld a válaszodat."
            )

    st.write("---")


# ─────────────────────────────────────────────────────────
# Kiértékelés (12-ből legalább 9 helyes)
def kiertet() -> None:
    helyes = sum(1 for k in kerdesek if itel.get(k) == "helyes")
    sikeres = helyes >= PASS_MIN
    st.session_state.osszegzes = {"helyes_db": helyes, "sikeres": sikeres}


st.button("🏁 Teszt kiértékelése", type="primary", on_click=kiertet)

if st.session_state.osszegzes is not None:
    helyes = st.session_state.osszegzes["helyes_db"]
    sikeres = st.session_state.osszegzes["sikeres"]
    if sikeres:
        st.success(f"✅ SIKERES TESZT — {helyes}/{len(kerdesek)} (minimum: {PASS_MIN})")
    else:
        st.error(
            f"❌ SIKERTELEN TESZT — {helyes}/{len(kerdesek)} (legalább {PASS_MIN} szükséges)"
        )

    # Eredmény export (JSON)
    export = {
        "kor_id": "session",
        "mod": MODE_LABELS[mod],
        "sorrend": "CSV eredeti sorrendje",
        "kerdesek_szama": len(kerdesek),
        "minimum_helyes": PASS_MIN,
        "helyes_db": helyes,
        "sikeres": sikeres,
        "reszletek": [
            {
                "kerdes": k,
                "elfogadhato_valaszok": qa.get(k, []),
                "magyarazat": short_explanation(k, qa.get(k, [])),
                "itel": itel.get(k),
            }
            for k in kerdesek
        ],
    }
    st.download_button(
        label="📥 Eredmények letöltése (JSON)",
        data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="molek_sejtbiologia_eredmeny.json",
        mime="application/json",
        use_container_width=True,
    )

# CSV export
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["index", "question", "mark", "answers", "explanation"])
for i, kk in enumerate(kerdesek, 1):
    mark = itel.get(kk)
    mark_str = "" if mark is None else ("correct" if mark == "helyes" else "wrong")
    answers = qa.get(kk, [])
    joined = " | ".join(str(a).replace("\n", " ") for a in answers)
    w.writerow([i, kk, mark_str, joined, short_explanation(kk, answers)])
st.download_button(
    label="⬇️ Eredmények letöltése (CSV)",
    data=buf.getvalue(),
    file_name="molek_sejtbiologia_eredmeny.csv",
    mime="text/csv",
    use_container_width=True,
)
