// One hop around a fact: related facts (current versions only), described components, and code repos. Params: $id.
MATCH (f:KbFact {id: $id})
RETURN f.id AS id,
       [(f)-[r:KB_RELATES_TO]->(o:KbFact)-[:KB_HAS_VERSION]->(ov:KbCurrent) |
          {direction: 'out', rel: r.rel, id: o.id, title: ov.title, summary: ov.summary}]
     + [(f)<-[r:KB_RELATES_TO]-(o:KbFact)-[:KB_HAS_VERSION]->(ov:KbCurrent) |
          {direction: 'in', rel: r.rel, id: o.id, title: ov.title, summary: ov.summary}] AS facts,
       [(f)-[:KB_DESCRIBES]->(s:KbSystemComponent) |
          {name: s.name, kind: s.kind, description: s.description,
           repos: [(s)-[:KB_IMPLEMENTED_IN]->(r:KbCodeRepo) | r.path]}] AS components,
       [(f)-[:KB_IMPLEMENTED_IN]->(r:KbCodeRepo) | {path: r.path, web_url: r.web_url}] AS repos;
