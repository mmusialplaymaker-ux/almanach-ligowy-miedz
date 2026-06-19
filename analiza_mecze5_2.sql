-- analiza_mecze5_2.sql
-- Jak v5_1 + opponent/team_side liczone NIEZALEZNIE od pm_player_match_score
-- (z m.team_id vs matches.host_id/guest_id) -> dziala takze gdy brak rekordu score.
-- Na dole: opcjonalny, zakomentowany fallback z match_players (potwierdz kolumny).

WITH params AS (
    SELECT
        'e9d66181-d03e-4bb3-b889-4da848f4831d'::text AS season_id,   -- <<< :SEASON_ID
        '531b2ba4-d770-484f-b74f-027fd53a3919'::text AS play_id      -- <<< :PLAY_ID
),

roster AS (
    SELECT DISTINCT ps.player_id
    FROM pm_player_stats ps CROSS JOIN params prm
    WHERE ps.season_id = prm.season_id AND ps.play_id = prm.play_id
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
)

SELECT
    b.*,
    CASE
        WHEN b.is_junior_comp THEN NULL
        WHEN b.age_at_match IS NULL OR b.age_at_match NOT BETWEEN 12 AND 19 THEN NULL
        WHEN COALESCE(b.minutes, 0) > 0 THEN 'zagrał w seniorach'
        ELSE 'w kadrze seniorów'
    END                                                       AS status_seniorski,
    CASE
        WHEN NOT b.is_junior_comp THEN NULL
        WHEN b.est_birth_year IS NULL OR b.play_cohort_birth_year IS NULL THEN NULL
        WHEN (b.est_birth_year - b.play_cohort_birth_year) > 4
          OR (b.est_birth_year - b.play_cohort_birth_year) < -3 THEN NULL
        WHEN (b.est_birth_year - b.play_cohort_birth_year) >= 1 THEN TRUE
        ELSE FALSE
    END                                                       AS gra_ze_starszymi
FROM (
    SELECT
        m._id AS match_stat_id,
        m.match_id,
        m.player_id,
        p.firstname,
        p.lastname,
        m.play_id,
        pl.name AS play_name,
        rg.name AS region_name,
        m.team_id,
        t.name AS team_name,
        m.club_id,
        c.name AS club_name,
        m.league_id,
        l.name AS league_name,
        m.match_date,
        -- jesli wpinasz match_players, owin to w COALESCE (patrz blok na dole):
        m.minutes,
        m.goals,
        m.yellow_cards,
        m.red_cards,
        CASE m.result
            WHEN 0 THEN 'wygrana' WHEN 1 THEN 'remis' WHEN 2 THEN 'porażka' ELSE 'unknown'
        END AS match_result,

        -- ── STRONA i PRZECIWNIK niezaleznie od score'a ──
        -- preferuj s.team_side, a gdy brak -> wylicz z m.team_id vs matches.host/guest
        CASE COALESCE(s.team_side,
                      CASE WHEN m.team_id = mat.host_id  THEN 'host'
                           WHEN m.team_id = mat.guest_id THEN 'guest' END)
            WHEN 'host'  THEN mat.guest_id
            WHEN 'guest' THEN mat.host_id  ELSE NULL END                  AS opponent_id,
        CASE COALESCE(s.team_side,
                      CASE WHEN m.team_id = mat.host_id  THEN 'host'
                           WHEN m.team_id = mat.guest_id THEN 'guest' END)
            WHEN 'host'  THEN guest_team.name
            WHEN 'guest' THEN host_team.name ELSE 'unknown' END           AS opponent_name,
        CASE COALESCE(s.team_side,
                      CASE WHEN m.team_id = mat.host_id  THEN 'host'
                           WHEN m.team_id = mat.guest_id THEN 'guest' END)
            WHEN 'host'  THEN 'gospodarz'
            WHEN 'guest' THEN 'gość' ELSE 'unknown' END                   AS team_side,

        CASE WHEN s.score = 'NaN'::double precision THEN NULL ELSE s.score END AS match_score,
        s.overall_score AS m_overall_score,
        s.season_score  AS m_season_score,
        s.calculation_version AS calc_version,
        s.age AS player_age,

        (m.play_id = prm.play_id)                             AS in_selected_play,
        CASE
            WHEN l.name ~* '^(A1|A2|B1|B2|C1|C2|D1|D2)$'
                 OR l.name ILIKE 'CLJ%' OR l.name ILIKE '%U-1%'
                 OR pl.name ~* '(junior|trampkarz|m[lł]odzik|[zż]ak|orlik|skrzat)'
            THEN TRUE ELSE FALSE
        END                                                   AS is_junior_comp,

        substring(p.date_of_birth::text from '[0-9]{4}')::int AS est_birth_year,
        (substring(m.match_date::text from '[0-9]{4}')::int
            - substring(p.date_of_birth::text from '[0-9]{4}')::int) AS age_at_match,
        pr.cohort_birth_year                                  AS play_cohort_birth_year,
        pr.cohort_n_players                                   AS play_cohort_n_players

    FROM pm_player_match_stats m
    CROSS JOIN params prm
    LEFT JOIN pm_player_match_score s
        ON m.match_id = s.match_id AND m.player_id = s.player_id AND m.season_id = s.season_id
    LEFT JOIN plays pl ON m.play_id = pl._id
    LEFT JOIN regions rg ON pl.region_id = rg._id
    LEFT JOIN teams t ON m.team_id = t._id
    LEFT JOIN clubs c ON m.club_id = c._id
    LEFT JOIN leagues l ON m.league_id = l._id
    LEFT JOIN players p ON m.player_id = p._id
    LEFT JOIN matches mat ON m.match_id = mat._id
    LEFT JOIN teams host_team ON mat.host_id = host_team._id
    LEFT JOIN teams guest_team ON mat.guest_id = guest_team._id
    LEFT JOIN play_ref pr ON m.play_id = pr.play_id

    -- ============================================================
    -- OPCJONALNY FALLBACK Z match_players (odkomentuj po potwierdzeniu kolumn)
    -- Zaklada klucz (match_id, player_id) i kolumny minutes/goals/...
    -- LEFT JOIN match_players mp
    --     ON mp.match_id = m.match_id AND mp.player_id = m.player_id
    -- a powyzej w SELECT podmien:
    --     m.minutes      -> COALESCE(m.minutes,      mp.minutes)
    --     m.goals        -> COALESCE(m.goals,        mp.goals)
    --     m.yellow_cards -> COALESCE(m.yellow_cards, mp.yellow_cards)
    --     m.red_cards    -> COALESCE(m.red_cards,    mp.red_cards)
    -- ============================================================

    WHERE m.season_id = prm.season_id
      AND m.player_id IN (SELECT player_id FROM roster)
) b
ORDER BY b.match_id, b.player_id;
