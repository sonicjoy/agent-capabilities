// Whether a fact id is taken (the ingest skips existing facts). Params: $id.
RETURN EXISTS { (:KbFact {id: $id}) } AS exists;
