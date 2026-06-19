-- analiza_stats5_1.sql
-- Sparametryzowane: season_id + play_id. Roster wybranego play + wszystkie ich mecze sezonu (agregaty per play).
-- Nowe: rollup ekspozycji seniorskiej (kadra vs realne minuty).

WITH params AS (
    SELECT
        'e9d66181-d03e-4bb3-b889-4da848f4831d'::text AS season_id,   -- <<< :SEASON_ID
        '531b2ba4-d770-484f-b74f-027fd53a3919'::text AS play_id      -- <<< :PLAY_ID  (2 liga wojewodzka A1)
),

roster AS (
    SELECT DISTINCT ps.player_id
    FROM pm_player_stats ps CROSS JOIN params prm
    WHERE ps.season_id = prm.season_id
      AND ps.play_id   = prm.play_id
),

play_ref AS (
    SELECT pst.play_id,
           mode() WITHIN GROUP (
               ORDER BY substring(pp.date_of_birth::text from '[0-9]{4}')::int
           )                                          AS cohort_birth_year,
           COUNT(DISTINCT pst.player_id)              AS cohort_n_players
    FROM pm_player_stats pst
    JOIN players pp ON pp._id = pst.player_id
    CROSS JOIN params prm
    WHERE pst.season_id = prm.season_id
      AND substring(pp.date_of_birth::text from '[0-9]{4}') IS NOT NULL
    GROUP BY pst.play_id
),

-- klasyfikacja kazdego meczu rostera: liga juniorska? wiek w dniu meczu?
match_class AS (
    SELECT m.player_id,
           m.minutes,
           CASE
               WHEN l.name ~* '^(A1|A2|B1|B2|C1|C2|D1|D2)$'
                    OR l.name ILIKE 'CLJ%' OR l.name ILIKE '%U-1%'
                    OR pl.name ~* '(junior|trampkarz|m[lł]odzik|[zż]ak|orlik|skrzat)'
               THEN TRUE ELSE FALSE
           END AS is_jr,
           (substring(m.match_date::text from '[0-9]{4}')::int
               - substring(p.date_of_birth::text from '[0-9]{4}')::int) AS age_m
    FROM pm_player_match_stats m
    CROSS JOIN params prm
    LEFT JOIN leagues l ON m.league_id = l._id
    LEFT JOIN plays pl ON m.play_id = pl._id
    LEFT JOIN players p ON m.player_id = p._id
    WHERE m.season_id = prm.season_id
      AND m.player_id IN (SELECT player_id FROM roster)
),

-- rollup ekspozycji w rozgrywkach seniorskich (junior <=19 w dniu meczu)
senior_exposure AS (
    SELECT player_id,
           COUNT(*) FILTER (WHERE NOT is_jr AND age_m BETWEEN 12 AND 19)
               AS senior_squad_apps,
           COUNT(*) FILTER (WHERE NOT is_jr AND age_m BETWEEN 12 AND 19 AND COALESCE(minutes,0) > 0)
               AS senior_matches_played,
           SUM(CASE WHEN NOT is_jr AND age_m BETWEEN 12 AND 19 THEN COALESCE(minutes,0) ELSE 0 END)
               AS senior_minutes
    FROM match_class
    GROUP BY player_id
)

SELECT
    b.*,
    CASE WHEN b.is_junior_comp THEN (b.est_birth_year - b.play_cohort_birth_year) END
                                                              AS roczniki_w_gore,
    CASE
        WHEN NOT b.is_junior_comp THEN NULL
        WHEN b.est_birth_year IS NULL OR b.play_cohort_birth_year IS NULL THEN NULL
        WHEN (b.est_birth_year - b.play_cohort_birth_year) > 4
          OR (b.est_birth_year - b.play_cohort_birth_year) < -3 THEN NULL
        WHEN (b.est_birth_year - b.play_cohort_birth_year) >= 1 THEN TRUE
        ELSE FALSE
    END                                                       AS gra_ze_starszymi
FROM (
    SELECT DISTINCT ON (ps.player_id, ps.play_id, ps.team_id)
        ps.*,
        p.firstname,
        p.lastname,
        p.date_of_birth AS birth_date,
        pl.name AS play_name,
        rg.name AS region_name,
        t.name AS team_name,
        l.name AS league_name,
        c.name AS club_name,

        (ps.play_id = prm.play_id)                            AS in_selected_play,

        CASE
            WHEN l.name ~* '^(A1|A2|B1|B2|C1|C2|D1|D2)$'
                 OR l.name ILIKE 'CLJ%' OR l.name ILIKE '%U-1%'
                 OR pl.name ~* '(junior|trampkarz|m[lł]odzik|[zż]ak|orlik|skrzat)'
            THEN TRUE ELSE FALSE
        END                                                   AS is_junior_comp,

        NULLIF(ls.overall_score, 'NaN'::double precision)::numeric  AS overall_score,
        NULLIF(ls.season_score,  'NaN'::double precision)::numeric  AS season_score,
        ls.match_date          AS last_match_in_play,
        ls.calculation_version AS calc_version,
        NULLIF(gs.overall_score, 'NaN'::double precision)::numeric  AS global_last_overall_score,
        NULLIF(gs.season_score,  'NaN'::double precision)::numeric  AS global_last_season_score,
        gs.match_date          AS global_last_match_date,

        substring(p.date_of_birth::text from '[0-9]{4}')::int AS est_birth_year,
        pr.cohort_birth_year                                  AS play_cohort_birth_year,
        pr.cohort_n_players                                   AS play_cohort_n_players,

        -- ── ekspozycja seniorska (rollup per zawodnik) ──
        COALESCE(se.senior_squad_apps, 0)                     AS senior_squad_apps,     -- ile razy w kadrze seniorow
        COALESCE(se.senior_matches_played, 0)                 AS senior_matches_played, -- ile razy realnie zagral
        COALESCE(se.senior_minutes, 0)                        AS senior_minutes,        -- suma minut w seniorach
        CASE
            WHEN COALESCE(se.senior_matches_played, 0) > 0 THEN 'zagrał w seniorach'
            WHEN COALESCE(se.senior_squad_apps, 0)     > 0 THEN 'w kadrze seniorów'
            ELSE NULL
        END                                                   AS status_seniorski

    FROM pm_player_stats ps
    CROSS JOIN params prm
    LEFT JOIN players p ON ps.player_id = p._id
    LEFT JOIN plays pl ON ps.play_id = pl._id
    LEFT JOIN regions rg ON pl.region_id = rg._id
    LEFT JOIN teams t ON ps.team_id = t._id
    LEFT JOIN leagues l ON ps.league_id = l._id
    LEFT JOIN clubs c ON ps.club_id = c._id

    LEFT JOIN (
        SELECT DISTINCT ON (player_id, play_id)
            player_id, play_id, overall_score, season_score, match_date, calculation_version
        FROM pm_player_match_score
        ORDER BY player_id, play_id, match_date DESC
    ) ls ON ps.player_id = ls.player_id AND ps.play_id = ls.play_id

    LEFT JOIN (
        SELECT DISTINCT ON (player_id)
            player_id, overall_score, season_score, match_date
        FROM pm_player_match_score
        ORDER BY player_id, match_date DESC
    ) gs ON ps.player_id = gs.player_id

    LEFT JOIN play_ref        pr ON ps.play_id   = pr.play_id
    LEFT JOIN senior_exposure se ON ps.player_id = se.player_id

    WHERE ps.season_id = prm.season_id
      AND ps.player_id IN (SELECT player_id FROM roster)
    ORDER BY ps.player_id, ps.play_id, ps.team_id, ps.updated_at DESC
) b
ORDER BY b.player_id, b.play_id, b.team_id;
