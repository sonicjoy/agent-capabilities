// Draft -> active and current, approved by $approver. Record time starts now. Params: $vid, $now, $approver,
// $approver_name, $recorded_by, $evidence. $recorded_by and $evidence are set when the author promoted their own
// draft on $approver's confirmation (null otherwise, which leaves the properties unset).
MATCH (d:KbFactVersion {version_id: $vid, status: 'draft'})
MERGE (p:KbPerson {email: $approver}) ON CREATE SET p.name = $approver_name
CREATE (d)-[:KB_APPROVED_BY]->(p)
SET d.status = 'active', d.recorded_at = $now, d:KbCurrent,
    d.approval_recorded_by = $recorded_by, d.approval_evidence = $evidence
RETURN d.version_id AS version_id;
