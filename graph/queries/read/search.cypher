// Search current facts. Params: $words (one list of variants per query word, e.g. [['pool'], ['restarts','restart']],
// prepared by kb.py), $limit.
// The TEXT index on :KbCurrent(search_text) is sought once per variant (UNWIND + Apply). Each word then scores once,
// by its best variant: title 4, keywords 3, summary 2, statement 1 (a stem never doubles a word's weight).
UNWIND $words AS word
UNWIND word AS term
MATCH (v:KbCurrent) WHERE v.search_text CONTAINS term
WITH DISTINCT v
MATCH (f:KbFact)-[:KB_HAS_VERSION]->(v)
MATCH (f)-[:KB_IN_CATEGORY]->(c:KbCategory)
WITH f, v, c, toLower(v.title) AS title, [k IN coalesce(v.keywords, []) | toLower(k)] AS keywords,
     toLower(v.summary) AS summary, toLower(v.statement) AS statement
WITH f, v, c, reduce(score = 0, word IN $words | score + reduce(best = 0, s IN [t IN word |
         CASE WHEN title CONTAINS t THEN 4 ELSE 0 END
       + CASE WHEN any(k IN keywords WHERE k CONTAINS t) THEN 3 ELSE 0 END
       + CASE WHEN summary CONTAINS t THEN 2 ELSE 0 END
       + CASE WHEN statement CONTAINS t THEN 1 ELSE 0 END] | CASE WHEN s > best THEN s ELSE best END)) AS score
RETURN f.id AS id, v.title AS title, v.summary AS summary, v.kind AS kind, c.path AS category, score
ORDER BY score DESC, title
LIMIT $limit;
