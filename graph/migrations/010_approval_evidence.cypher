// 010 — types for the approval a draft's author records when they promote it themselves (#29). Idempotent.
// approval_recorded_by: who ran the promote; approval_evidence: link to the approver's confirmation.

CREATE CONSTRAINT kb_fv_approval_recorded_by_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.approval_recorded_by IS :: STRING;
CREATE CONSTRAINT kb_fv_approval_evidence_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.approval_evidence IS :: STRING;
