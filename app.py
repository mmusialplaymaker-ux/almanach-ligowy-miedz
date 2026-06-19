"""
PlayMaker Pro - dashboard skautingowy (prototyp).
Uklad: filtry -> karty topowych (scroll w bok) -> tabela graczy -> klikalne mecze.

Uruchomienie:
    pip install -r requirements.txt
    streamlit run app.py   # pliki: stats_test.csv, matches_test.csv, teamy_kluby_25_26.csv
"""
import os
import numpy as np
import pandas as pd
import streamlit as st

def _secret(key, default=""):
    """Czyta najpierw st.secrets (Streamlit Cloud), potem zmienne środowiskowe."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


DATA_MODE = _secret("PM_DATA_MODE", "csv") or "csv"
REGION = _secret("PM_REGION", "")   # region wybrany na wejsciu (region -> liga -> play)

NUMERIC_COMMA = ["match_score", "m_overall_score", "m_season_score", "overall_score",
                 "season_score", "global_last_overall_score", "global_last_season_score"]
NUMERIC_PLAIN = ["minutes", "goals", "yellow_cards", "red_cards", "est_birth_year",
                 "age_at_match", "senior_minutes", "senior_matches_played",
                 "senior_squad_apps", "play_cohort_birth_year", "matches_count"]
PM_WEIGHTS = {"Jakość": 0.50, "Forma": 0.20, "Dostępność": 0.15, "Konsekwencja": 0.15}
# premie kontekstowe doliczane do bazy PM Index (tunable)
B_UP = 0.05          # gra ze starszymi rocznikiem (junior w gore)
B_SEN_SQUAD = 0.04   # w kadrze seniorow (0 minut)
B_SEN_PLAYED = 0.12  # realne minuty w seniorach
PM_HELP = (
    "**PM Index** to wskaźnik pozycji zawodnika względem stawki tej ligi — im wyżej, tym "
    "lepiej wypada na tle rywali. Baza (zwykle 0–1) to ważona suma czterech percentyli "
    "liczonych w obrębie wybranej ligi:\n\n"
    "- **Jakość (50%)** — średnia ocena meczu (PM Score) w lidze.\n\n"
    "- **Forma (20%)** — średnia ocena z 5 ostatnich meczów względem średniej z całego sezonu "
    "w tej lidze (dodatnia = forma rosnąca, ujemna = spadek).\n\n"
    "- **Dostępność (15%)** — łączne minuty rozegrane w lidze; jak regularnie zawodnik gra "
    "(zaufanie trenera, zdrowie, rola w zespole).\n\n"
    "- **Konsekwencja (15%)** — stabilność ocen meczowych (mała zmienność = równy poziom).\n\n"
    "Do bazy doliczana jest **premia kontekstowa** (kolumna „Premia”): "
    f"+{B_UP:.2f} za grę ze starszymi rocznikiem, +{B_SEN_SQUAD:.2f} za obecność w kadrze "
    f"seniorów, +{B_SEN_PLAYED:.2f} za realne minuty w seniorach (premie się sumują). "
    "Dlatego PM Index z premią może nieco przekroczyć 1."
)

CSS = """
<style>
.pmrow{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 12px;}
.pmcard{flex:0 0 232px;border:1px solid #2b3340;border-radius:12px;padding:12px 14px;
        background:#191f29;}
.pmcard h4{margin:0 0 2px;font-size:15px;color:#e8edf4;}
.pmcard .sub{font-size:12px;color:#9aa7b6;margin-bottom:8px;height:30px;overflow:hidden;}
.pmcard .pm{font-size:22px;font-weight:700;color:#5db0ff;}
.pmcard .pmlbl{font-size:10px;color:#8a97a6;letter-spacing:.5px;text-transform:uppercase;}
.pmcard .row{font-size:12px;color:#c4cdd8;margin-top:6px;}
.pmcard .badges{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;}
.b{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;white-space:nowrap;}
.b.up{background:#2a2150;color:#c4b5fd;}
.b.sen{background:#16361f;color:#7ee2a0;}
.b.kad{background:#3a2f14;color:#e6c674;}
/* rozwijana lista filtrow: zawijaj dlugie nazwy zamiast ucinac */
div[data-baseweb="menu"] li{white-space:normal!important;height:auto!important;line-height:1.35;}
div[data-baseweb="popover"] ul{max-height:420px;}
</style>
"""

BADGE_HELP = (
    "**↑ ze starszymi** — junior grający w starszym roczniku niż dominujący w jego lidze.\n\n"
    "**🪑 kadra seniorów** — był w meczowej kadrze seniorów, ale rozegrał 0 minut.\n\n"
    "**⚽ minuty w seniorach** — rozegrał realne minuty w rozgrywkach seniorskich (na karcie z liczbą minut)."
)


# --------------------------------------------------------------------------- #
def _read_csv(path):
    for enc in ("utf-8", "cp1250", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="latin-1")


def _coerce(df):
    for c in NUMERIC_COMMA:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False)
                                  .replace({"NULL": None, "": None, "NaN": None}), errors="coerce")
    for c in NUMERIC_PLAIN:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].replace({"NULL": None, "": None}), errors="coerce")
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    for c in ["in_selected_play", "is_junior_comp", "gra_ze_starszymi"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.lower().map({"true": True, "false": False})
    return df


def _clean_names(df, tk):
    tmap = dict(zip(tk["team_id"], tk["final_team_name"]))
    cmap = dict(zip(tk["club_id"], tk["final_club_name"]))
    if "team_id" in df.columns:
        df["team_name"] = df["team_id"].map(tmap).fillna(df.get("team_name"))
    if "club_id" in df.columns:
        df["club_name"] = df["club_id"].map(cmap).fillna(df.get("club_name"))
    if "opponent_id" in df.columns:
        df["opponent_name"] = df["opponent_id"].map(tmap).fillna(df.get("opponent_name"))
    return df


@st.cache_data(show_spinner=False)
def load_data(stats_path="stats_test.csv", matches_path="matches_test.csv",
              teamy_path="teamy_kluby_25_26.csv"):
    if DATA_MODE == "db":
        return load_from_db()
    stats, matches = _coerce(_read_csv(stats_path)), _coerce(_read_csv(matches_path))
    if os.path.exists(teamy_path):
        tk = _read_csv(teamy_path)
        stats, matches = _clean_names(stats, tk), _clean_names(matches, tk)
    return stats, matches


def load_from_db(season_id=None, play_id=None):
    import psycopg2
    conn = psycopg2.connect(host=_secret("PGHOST"), dbname=_secret("PGDATABASE"),
                            user=_secret("PGUSER"), password=_secret("PGPASSWORD"),
                            port=_secret("PGPORT", "5432") or "5432")
    p = {"season_id": season_id, "play_id": play_id}
    stats = _coerce(pd.read_sql(open("analiza_stats5_1.sql").read(), conn, params=p))
    matches = _coerce(pd.read_sql(open("analiza_mecze5_2.sql").read(), conn, params=p))
    conn.close()
    return stats, matches


# --------------------------------------------------------------------------- #
def _attrs(stats):
    sel = stats[stats["in_selected_play"] == True].copy()
    sel["zawodnik"] = (sel["firstname"].fillna("") + " " + sel["lastname"].fillna("")).str.strip()
    cols = ["player_id", "zawodnik", "team_name", "club_name", "league_name", "play_name",
            "est_birth_year", "gra_ze_starszymi", "status_seniorski", "senior_minutes",
            "senior_squad_apps", "roczniki_w_gore"]
    return sel[[c for c in cols if c in sel.columns]].drop_duplicates("player_id")


def _play_metrics(g):
    g = g.sort_values("match_date")
    mins, goals = g["minutes"].sum(), g["goals"].sum()
    cards = g["yellow_cards"].sum() + g["red_cards"].sum()
    cidx = g["yellow_cards"].sum() + 2 * g["red_cards"].sum()
    s = g["match_score"].dropna()
    forma = ((s.tail(5).mean() - s.mean()) / s.mean()) if len(s) >= 3 and s.mean() else np.nan
    return pd.Series({"min_play": mins, "mecze_play": g["match_id"].nunique(), "gole_play": goals,
                      "kartki_play": cards, "score_play": s.mean() if len(s) else np.nan,
                      "gole_per90": (goals / mins * 90) if mins else np.nan,
                      "kartki_per90": (cidx / mins * 90) if mins else np.nan,
                      "konsekwencja": (1 / (1 + s.std(ddof=0))) if len(s) >= 2 else np.nan,
                      "forma": forma})


def _total_metrics(g):
    mins, goals = g["minutes"].sum(), g["goals"].sum()
    s = g["match_score"].dropna()
    lead = (g.groupby("league_name")["minutes"].sum().idxmax()
            if g["minutes"].sum() > 0 and g["league_name"].notna().any() else None)
    return pd.Series({"min_total": mins, "mecze_total": g["match_id"].nunique(),
                      "gole_total": goals,
                      "kartki_total": g["yellow_cards"].sum() + g["red_cards"].sum(),
                      "score_total": s.mean() if len(s) else np.nan, "liga_wiodaca": lead})


@st.cache_data(show_spinner=False)
def build(_stats, _matches):
    attrs = _attrs(_stats)
    play = _matches[_matches["in_selected_play"] == True]
    base = play.groupby("player_id").apply(_play_metrics).reset_index()
    tot = _matches.groupby("player_id").apply(_total_metrics).reset_index()
    df = attrs.merge(base, on="player_id", how="left").merge(tot, on="player_id", how="left")
    df["Ofensywa"] = df["gole_per90"].rank(pct=True)
    df["Jakość"] = df["score_play"].rank(pct=True)
    df["Forma"] = df["forma"].rank(pct=True)
    df["Konsekwencja"] = df["konsekwencja"].rank(pct=True)
    df["Dostępność"] = df["min_play"].rank(pct=True)
    df["Dyscyplina"] = (-df["kartki_per90"]).rank(pct=True)
    df["PM_base"] = sum(df[a].fillna(0) * w for a, w in PM_WEIGHTS.items())
    sm = df["senior_minutes"].fillna(0)
    sq = df["senior_squad_apps"].fillna(0)
    df["PM_premia"] = ((df["gra_ze_starszymi"] == True).astype(float) * B_UP
                       + (sm > 0).astype(float) * B_SEN_PLAYED
                       + ((sm == 0) & (sq > 0)).astype(float) * B_SEN_SQUAD)
    df["PM_Index"] = df["PM_base"] + df["PM_premia"]
    lg = _matches.groupby("player_id")["league_name"].agg(lambda s: set(s.dropna()))
    pp = _matches.groupby("player_id")["play_name"].agg(lambda s: set(s.dropna()))
    df["_leagues"] = df["player_id"].map(lg)
    df["_plays"] = df["player_id"].map(pp)
    ry = _matches["match_date"].dt.year.max()
    df["_ref_year"] = int(ry) if pd.notna(ry) else 2026
    return df


def badges_html(r):
    out = []
    if r.get("gra_ze_starszymi") is True:
        out.append('<span class="b up">↑ ze starszymi</span>')
    sm = r.get("senior_minutes") or 0
    if sm > 0:
        out.append(f'<span class="b sen">⚽ {int(sm)}′ w seniorach</span>')
    elif (r.get("senior_squad_apps") or 0) > 0:
        out.append('<span class="b kad">🪑 kadra seniorów</span>')
    return "".join(out)


def cards_html(top):
    cards = []
    for _, r in top.iterrows():
        by = r.get("est_birth_year")
        age = f"{int(r['_ref_year'] - by)} lat" if pd.notna(by) else "—"
        rok = f"rocznik {int(by)}" if pd.notna(by) else ""
        klub = r.get("club_name") or r.get("team_name") or "—"
        lead = r.get("liga_wiodaca") or r.get("league_name") or "—"
        cards.append(
            f'<div class="pmcard"><h4>{r["zawodnik"]}</h4>'
            f'<div class="sub">{klub}<br>liga wiodąca: {lead}</div>'
            f'<div class="pmlbl">PM Index</div><div class="pm">{r["PM_Index"]:.2f}</div>'
            f'<div class="row">{rok} · {age}</div>'
            f'<div class="row">{int(r.get("min_total") or 0)} min · {int(r.get("mecze_total") or 0)} meczów (sezon)</div>'
            f'<div class="badges">{badges_html(r)}</div></div>')
    return '<div class="pmrow">' + "".join(cards) + "</div>"


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
def check_password():
    """Lekka bramka: jesli ustawiono APP_PASSWORD (st.secrets lub env) - wymagaj.
    Brak hasla = otwarte (lokalnie)."""
    pw = _secret("APP_PASSWORD")
    if not pw:
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.title("Almanach ligowy")
    with st.form("login"):
        x = st.text_input("Hasło dostępu", type="password")
        if st.form_submit_button("Wejdź"):
            if x == str(pw):
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Błędne hasło.")
    return False


def main():
    st.set_page_config(page_title="Almanach ligowy", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if not check_password():
        st.stop()
    stats, matches = load_data()
    data = build(stats, matches)

    sel_mask = stats["in_selected_play"] == True
    liga = stats.loc[sel_mask, "play_name"].dropna().iloc[0] if sel_mask.any() else "—"
    region = ""
    if "region_name" in stats.columns:
        rr = stats.loc[sel_mask, "region_name"].dropna()
        region = rr.iloc[0] if len(rr) else ""
    region = region or REGION
    st.title("Almanach ligowy")
    reg = f"Region: **{region}**  ·  " if region else ""
    st.markdown(f"{reg}**{liga}** · zawodników: {len(data)} · "
                f"z minutami w seniorach: {(data['senior_minutes'].fillna(0) > 0).sum()}")
    st.caption("Wszyscy zawodnicy z wybranej ligi wraz z meczami w bieżącym sezonie "
               "we wszystkich rozgrywkach. Kolumny „(liga)” dotyczą wybranej ligi, "
               "„(total)” — całego sezonu.")

    # ---- FILTRY ----
    with st.container(border=True):
        r1 = st.columns([2, 2, 2])
        q = r1[0].text_input("Zawodnik (imię/nazwisko)", "")
        f_club = r1[1].multiselect("Klub", sorted(data["club_name"].dropna().unique()))
        f_lg = r1[2].multiselect("Rozgrywki (gdziekolwiek grał)",
                                 sorted({x for s in data["_leagues"].dropna() for x in s}))
        f_pl = st.multiselect("Liga (gdziekolwiek grał)",
                              sorted({x for s in data["_plays"].dropna() for x in s}))
        r2 = st.columns(4)
        def rng(col, label, c):
            lo, hi = float(np.nanmin(data[col])), float(np.nanmax(data[col]))
            if not np.isfinite(lo) or lo == hi:
                return (lo, hi)
            return c.slider(label, lo, hi, (lo, hi))
        s_score = rng("score_play", "Score (liga)", r2[0])
        s_min = rng("min_play", "Minuty (liga)", r2[1])
        s_mecz = rng("mecze_play", "Mecze (liga)", r2[2])
        s_kart = rng("kartki_total", "Kartki total", r2[3])
        r3 = st.columns(3)
        f_up = r3[0].checkbox("↑ Grający ze starszymi")
        f_kad = r3[1].checkbox("🪑 W kadrze seniorów")
        f_sen = r3[2].checkbox("⚽ Minuty w seniorach")

    # ---- FILTROWANIE ----
    f = data.copy()
    if q:
        f = f[f["zawodnik"].str.contains(q, case=False, na=False)]
    if f_club:
        f = f[f["club_name"].isin(f_club)]
    if f_lg:
        f = f[f["_leagues"].apply(lambda s: bool(s & set(f_lg)) if isinstance(s, set) else False)]
    if f_pl:
        f = f[f["_plays"].apply(lambda s: bool(s & set(f_pl)) if isinstance(s, set) else False)]
    for col, (lo, hi) in [("score_play", s_score), ("min_play", s_min),
                          ("mecze_play", s_mecz), ("kartki_total", s_kart)]:
        f = f[f[col].fillna(-1).between(lo, hi) | f[col].isna()]
    if f_up:
        f = f[f["gra_ze_starszymi"] == True]
    if f_kad:
        f = f[(f["senior_squad_apps"].fillna(0) > 0) & (f["senior_minutes"].fillna(0) == 0)]
    if f_sen:
        f = f[f["senior_minutes"].fillna(0) > 0]
    f = f.sort_values("PM_Index", ascending=False).reset_index(drop=True)

    # ---- KARTY TOPOWYCH (scroll w bok) ----
    st.markdown("### 🏅 Topowi zawodnicy")
    if len(f):
        st.markdown(cards_html(f.head(15)), unsafe_allow_html=True)
    else:
        st.info("Brak zawodników dla wybranych filtrów.")

    # ---- TABELA ----
    st.markdown("### 📋 Analityka")
    ci = st.columns([2, 2, 6])
    with ci[0].popover("ℹ️ Czym jest PM Index?"):
        st.markdown(PM_HELP)
    with ci[1].popover("🏷️ Znaczniki"):
        st.markdown(BADGE_HELP)

    def znaczniki(r):
        z = []
        if r.get("gra_ze_starszymi") is True: z.append("↑")
        if (r.get("senior_minutes") or 0) > 0: z.append("⚽")
        elif (r.get("senior_squad_apps") or 0) > 0: z.append("🪑")
        return " ".join(z)
    ft = f.copy()
    ft["Znaczniki"] = ft.apply(znaczniki, axis=1)
    cmap = {"zawodnik": "Zawodnik", "Znaczniki": "Znaczniki", "team_name": "Drużyna",
            "club_name": "Klub", "est_birth_year": "Rocznik", "PM_Index": "PM Index",
            "PM_premia": "Premia",
            "score_play": "Score (liga)", "score_total": "Score (total)",
            "min_play": "Min (liga)", "min_total": "Min (total)",
            "mecze_play": "Mecze (liga)", "mecze_total": "Mecze (total)",
            "gole_play": "Gole (liga)", "gole_total": "Gole (total)",
            "kartki_total": "Kartki", "senior_minutes": "Min. seniory"}
    disp = ft[[c for c in cmap if c in ft.columns]].rename(columns=cmap)
    event = st.dataframe(
        disp, use_container_width=True, height=430, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "PM Index": st.column_config.NumberColumn(format="%.2f", help=PM_HELP),
            "Premia": st.column_config.NumberColumn(format="%.2f",
                help="Premia kontekstowa doliczona do PM Index (gra ze starszymi / kadra / minuty w seniorach)."),
            "Score (liga)": st.column_config.NumberColumn(format="%.3f"),
            "Score (total)": st.column_config.NumberColumn(format="%.3f"),
            "Znaczniki": st.column_config.TextColumn(
                help="↑ gra ze starszymi · 🪑 w kadrze seniorów · ⚽ minuty w seniorach")})

    sel_pid = f.iloc[event.selection.rows[0]]["player_id"] if event.selection.rows else None

    # ---- MECZE ----
    if sel_pid:
        who = f.loc[f["player_id"] == sel_pid, "zawodnik"].iloc[0]
        st.markdown(f"### ⚽ Mecze: {who}")
        mm = matches[matches["player_id"] == sel_pid]
    else:
        st.markdown(f"### ⚽ Mecze ({len(f)} zawodników) — kliknij gracza wyżej, by zawęzić")
        mm = matches[matches["player_id"].isin(f["player_id"])]
    mc = {"match_date": "Data", "league_name": "Liga", "play_name": "Play",
          "team_name": "Drużyna", "opponent_name": "Przeciwnik", "team_side": "Strona",
          "match_result": "Wynik", "minutes": "Min", "goals": "Gole",
          "yellow_cards": "ŻK", "red_cards": "CK", "match_score": "Ocena",
          "status_seniorski": "Status senior"}
    mshow = (mm.sort_values("match_date", ascending=False)
               [[c for c in mc if c in mm.columns]].rename(columns=mc))
    st.dataframe(mshow, use_container_width=True, height=360, hide_index=True,
                 column_config={"Ocena": st.column_config.NumberColumn(format="%.3f")})


if __name__ == "__main__":
    main()
