// What a link source names: a fact id, a component name, or both. Params: $from.
RETURN EXISTS { (:KbFact {id: $from}) } AS fact, EXISTS { (:KbSystemComponent {name: $from}) } AS component;
