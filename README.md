# Almanach ligowy

Interaktywny raport skautingowy: dla wybranej ligi (sezon + play) pokazuje wszystkich
zawodników wraz z ich meczami w całym sezonie, znacznikami (gra ze starszymi / kadra /
minuty w seniorach) i wskaźnikiem **PM Index**.

## Uruchomienie lokalne

```bash
pip install -r requirements.txt
streamlit run app.py
```

Wymagane pliki w katalogu: `stats_test.csv`, `matches_test.csv`, `teamy_kluby_25_26.csv`.

## Konfiguracja (sekrety / zmienne)

| Klucz | Opis |
|---|---|
| `APP_PASSWORD` | Hasło dostępu. Ustawione → aplikacja pyta o hasło (ochrona linku). Puste → otwarte. |
| `PM_REGION` | Opcjonalna nazwa regionu w nagłówku (gdy nie ma jej jeszcze w danych). |
| `PM_DATA_MODE` | `csv` (domyślnie) lub `db`. |
| `PGHOST/PGDATABASE/PGUSER/PGPASSWORD/PGPORT` | Dane Postgresa dla trybu `db`. |

Lokalnie: skopiuj `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` i uzupełnij.

## Deploy na Streamlit Community Cloud

1. Wypchnij repo na GitHub (najlepiej **prywatne** — w środku są dane zawodników).
2. https://share.streamlit.io → **New app** → wskaż repo, branch `main`, plik `app.py`.
3. **App settings → Secrets**: wklej zawartość z `secrets.toml.example` z prawdziwymi wartościami
   (przynajmniej `APP_PASSWORD`).
4. Deploy → wyślij URL zespołowi. Hasło chroni dostęp.

## Tryby danych

- **csv** — czyta trzy pliki CSV z repo (prototyp).
- **db** — czyta na żywo z Postgresa zapytaniami `analiza_stats5_1.sql` / `analiza_mecze5_2.sql`
  (parametry `season_id` / `play_id`). Podmień literały w CTE `params` na `%(season_id)s` /
  `%(play_id)s` i ustaw sekrety `PG*`.

## Uwaga o prywatności
CSV zawierają dane zawodników — trzymaj repo **prywatne** albo używaj trybu `db` z sekretami.
