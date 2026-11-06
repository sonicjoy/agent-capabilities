// Colossus KB integrity checks. Every check must return zero rows.
// Format: each check starts with a `// check: <name>` line and is one read-only query returning (check, detail).
// `kb.py integrity` runs them in order and exits non-zero if any returns a row. Only Kb*/KB_* elements are read.

// check: multiple_current
MATCH (f:KbFact)-[:KB_HAS_VERSION]->(v:KbCurrent)
WITH f, count(v) AS n WHERE n > 1
RETURN 'multiple_current' AS check, f.id + ' has ' + n + ' :KbCurrent versions' AS detail;

// check: current_not_open_active
MATCH (v:KbCurrent)
WHERE NOT v:KbFactVersion OR v.status <> 'active' OR v.valid_to IS NOT NULL OR v.recorded_to IS NOT NULL
RETURN 'current_not_open_active' AS check, coalesce(v.version_id, elementId(v)) + ' status=' + coalesce(v.status, 'null') AS detail;

// check: active_not_current
MATCH (v:KbFactVersion {status: 'active'})
WHERE NOT v:KbCurrent
RETURN 'active_not_current' AS check, v.version_id AS detail;

// check: closed_without_recorded_to
MATCH (v:KbFactVersion)
WHERE v.status IN ['superseded', 'retracted'] AND v.recorded_to IS NULL
RETURN 'closed_without_recorded_to' AS check, v.version_id + ' status=' + v.status AS detail;

// check: retracted_without_valid_to
// Retracting ends the rule in business time as well as record time.
MATCH (v:KbFactVersion {status: 'retracted'})
WHERE v.valid_to IS NULL
RETURN 'retracted_without_valid_to' AS check, v.version_id AS detail;

// check: superseded_without_successor
// A superseded version must have exactly the version that replaced it pointing at it.
MATCH (v:KbFactVersion {status: 'superseded'})
WHERE NOT EXISTS { (:KbFactVersion)-[:KB_SUPERSEDES]->(v) }
RETURN 'superseded_without_successor' AS check, v.version_id AS detail;

// check: draft_closed
MATCH (v:KbFactVersion {status: 'draft'})
WHERE v.recorded_to IS NOT NULL OR v:KbCurrent
RETURN 'draft_closed' AS check, v.version_id AS detail;

// check: orphaned_history
// A fact with any non-draft version must have a current version, or end in a retraction that nothing superseded.
MATCH (f:KbFact)
WHERE EXISTS { (f)-[:KB_HAS_VERSION]->(x:KbFactVersion) WHERE x.status <> 'draft' }
  AND NOT EXISTS { (f)-[:KB_HAS_VERSION]->(:KbCurrent) }
  AND NOT EXISTS { (f)-[:KB_HAS_VERSION]->(r:KbFactVersion {status: 'retracted'}) WHERE NOT EXISTS { (:KbFactVersion)-[:KB_SUPERSEDES]->(r) } }
RETURN 'orphaned_history' AS check, f.id AS detail;

// check: fact_without_versions
MATCH (f:KbFact)
WHERE NOT EXISTS { (f)-[:KB_HAS_VERSION]->(:KbFactVersion) }
RETURN 'fact_without_versions' AS check, f.id AS detail;

// check: version_owner
MATCH (v:KbFactVersion)
WITH v, COUNT { (:KbFact)-[:KB_HAS_VERSION]->(v) } AS owners
WHERE owners <> 1
RETURN 'version_owner' AS check, v.version_id + ' belongs to ' + owners + ' facts' AS detail;

// check: fact_category_count
MATCH (f:KbFact)
WITH f, COUNT { (f)-[:KB_IN_CATEGORY]->(:KbCategory) } AS n
WHERE n <> 1
RETURN 'fact_category_count' AS check, f.id + ' is in ' + n + ' categories' AS detail;

// check: fact_in_non_leaf_category
MATCH (f:KbFact)-[:KB_IN_CATEGORY]->(c:KbCategory)
WHERE EXISTS { MATCH (child:KbCategory) WHERE child.path STARTS WITH c.path + '/' }
RETURN 'fact_in_non_leaf_category' AS check, f.id + ' -> ' + c.path AS detail;

// check: category_outside_library
MATCH (c:KbCategory)
WHERE COUNT { (c)-[:KB_PART_OF]->(:KbLibrary) } <> 1
RETURN 'category_outside_library' AS check, c.path AS detail;

// check: empty_required_text
MATCH (v:KbFactVersion)
WHERE trim(v.title) = '' OR trim(v.summary) = '' OR trim(v.statement) = '' OR size(v.source_refs) = 0
   OR any(r IN v.source_refs WHERE trim(r) = '')
   OR any(k IN coalesce(v.keywords, []) WHERE trim(k) = '')
RETURN 'empty_required_text' AS check, v.version_id AS detail;

// check: stale_search_text
// search_text must be the lower-cased title, summary, keywords and statement (see migration 007).
MATCH (v:KbFactVersion)
WHERE v.search_text <> toLower(v.title + '\n' + v.summary + '\n'
        + reduce(acc = '', k IN coalesce(v.keywords, []) | acc + CASE acc WHEN '' THEN '' ELSE ' ' END + k)
        + '\n' + v.statement)
RETURN 'stale_search_text' AS check, v.version_id AS detail;

// check: bad_enum
MATCH (v:KbFactVersion)
WHERE NOT v.status IN ['draft', 'active', 'superseded', 'retracted']
   OR NOT v.change_type IN ['create', 'change', 'correction']
   OR NOT v.kind IN ['rule', 'decision', 'description', 'procedure', 'glossary', 'lesson']
   OR NOT v.confidence IN ['verified', 'inferred', 'legacy_ingest']
   OR NOT v.via IN ['human', 'agent', 'ingest']
RETURN 'bad_enum' AS check, v.version_id + ' status=' + v.status + ' change_type=' + v.change_type + ' kind=' + v.kind
       + ' confidence=' + v.confidence + ' via=' + v.via AS detail;

// check: business_overlap
// Within a fact, versions that count for business time (not drafts, not replaced by a correction, not zero-length
// never-valid retractions) must not overlap: --as-of would otherwise have two answers.
MATCH (f:KbFact)-[:KB_HAS_VERSION]->(a:KbFactVersion), (f)-[:KB_HAS_VERSION]->(b:KbFactVersion)
WHERE a.version_id < b.version_id AND a.status <> 'draft' AND b.status <> 'draft'
  AND NOT EXISTS { (:KbFactVersion {change_type: 'correction'})-[:KB_SUPERSEDES]->(a) }
  AND NOT EXISTS { (:KbFactVersion {change_type: 'correction'})-[:KB_SUPERSEDES]->(b) }
  AND (a.valid_to IS NULL OR a.valid_from < a.valid_to) AND (b.valid_to IS NULL OR b.valid_from < b.valid_to)
  AND (a.valid_to IS NULL OR b.valid_from < a.valid_to) AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
RETURN 'business_overlap' AS check, f.id + ': ' + a.version_id + ' overlaps ' + b.version_id AS detail;

// check: future_dated
MATCH (v:KbFactVersion)
WHERE v.valid_from > v.recorded_at
RETURN 'future_dated' AS check, v.version_id AS detail;

// check: inverted_interval
MATCH (v:KbFactVersion)
WHERE (v.valid_to IS NOT NULL AND v.valid_to < v.valid_from)
   OR (v.recorded_to IS NOT NULL AND v.recorded_to < v.recorded_at)
RETURN 'inverted_interval' AS check, v.version_id AS detail;

// check: branching_supersedes
MATCH (old:KbFactVersion)
WITH old, COUNT { (:KbFactVersion)-[:KB_SUPERSEDES]->(old) } AS n
WHERE n > 1
RETURN 'branching_supersedes' AS check, old.version_id + ' superseded by ' + n + ' versions' AS detail;

// check: supersedes_many
// A version replaces at most one earlier version.
MATCH (new:KbFactVersion)
WITH new, COUNT { (new)-[:KB_SUPERSEDES]->(:KbFactVersion) } AS n
WHERE n > 1
RETURN 'supersedes_many' AS check, new.version_id + ' supersedes ' + n + ' versions' AS detail;

// check: draft_supersedes
// Drafts get their KB_SUPERSEDES edge when they are promoted, not when they are written.
MATCH (d:KbFactVersion {status: 'draft'})-[:KB_SUPERSEDES]->()
RETURN 'draft_supersedes' AS check, d.version_id AS detail;

// check: supersedes_across_facts
MATCH (f1:KbFact)-[:KB_HAS_VERSION]->(new:KbFactVersion)-[:KB_SUPERSEDES]->(old:KbFactVersion)<-[:KB_HAS_VERSION]-(f2:KbFact)
WHERE f1 <> f2
RETURN 'supersedes_across_facts' AS check, new.version_id + ' (' + f1.id + ') -> ' + old.version_id + ' (' + f2.id + ')' AS detail;

// check: missing_author
MATCH (v:KbFactVersion)
WHERE COUNT { (v)-[:KB_AUTHORED_BY]->(:KbPerson) } <> 1
RETURN 'missing_author' AS check, v.version_id AS detail;

// check: bad_relates_to
MATCH (:KbFact)-[r:KB_RELATES_TO]->(:KbFact)
WHERE r.rel IS NULL OR NOT r.rel IN ['depends_on', 'see_also', 'contradicts', 'example_of']
RETURN 'bad_relates_to' AS check, elementId(r) + ' rel=' + coalesce(r.rel, 'null') AS detail;
