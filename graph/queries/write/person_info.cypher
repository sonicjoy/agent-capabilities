// A person already in the KB, so a mistyped --confirmed-by isn't recorded as a new approver. Params: $email.
MATCH (p:KbPerson {email: $email})
RETURN p.email AS email, p.name AS name;
