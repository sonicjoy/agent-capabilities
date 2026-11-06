<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Fix Duplicated Data Using SQL Scripts

**Added**: 2026-03-05
**Context**: cbstatsfeed GitLab issue #196 – InvalidOperationException "Sequence contains more than one element" from duplicate competitor/feed data.
**Id**: `fix-duplicated-data-using-sql-scripts`

When duplicated data causes runtime errors (e.g. `.Single()` throwing), fix the data at source using SQL scripts rather than only making the application tolerant (e.g. `.First()` or "use first and log"). Use scripts to identify and remove or merge duplicates in the database so the application can continue to assume a single row where the domain expects one.
