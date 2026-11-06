// 003 — the colossus-bets library and its category tree, seeded from knowledge/colossus-bets/. Idempotent.
// Folders and entry files both become categories (`path` = folder or file path without `.md`). Facts attach only to
// leaf categories (no child categories), so the export keeps one markdown file per leaf. Titles and descriptions are
// set on create only; later edits go through kb.py.

MERGE (l:KbLibrary {name: 'colossus-bets'})
  ON CREATE SET l.title = 'Colossus Bets',
                l.description = 'Tote pools, cbtote, engine, commingling, StatsFeed and agent workflow.';

UNWIND [
  // ---- business
  {path: 'business', title: 'Business', description: 'Business rules and domain logic.'},
  {path: 'business/pools', title: 'Pool Business Rules', description: 'Tote pool rules: pool categories (leg-per-event, SEP, Fantasy, MVP), withdrawals, favourites, unit allocation, event ordering, pool restarts.'},
  {path: 'business/glossary', title: 'Glossary', description: 'Domain terms for PMs and engineers (SEP, MVP, RU, commingling host/guest, leg official, ...).'},
  // ---- technical
  {path: 'technical', title: 'Technical', description: 'Architecture, conventions, cbtote, workflow, tools and debugging.'},
  {path: 'technical/architecture', title: 'Architecture', description: 'System architecture and event flow.'},
  {path: 'technical/architecture/commingling', title: 'Commingling (general)', description: 'Replicating host actions to guest totes: local vs global Kafka, host/guest roles, commingled_* mapping, CFS and console roles.'},
  {path: 'technical/architecture/commingling-ticket-files', title: 'Commingling ticket files', description: 'Upload bucket shared by all gateways, sharedPools from SharedPoolGateways, TicketsReady logic, file naming.'},
  {path: 'technical/architecture/event-flow', title: 'Sport Event History Flow', description: 'Sport event status changes flow Console → Kafka → Engine.'},
  {path: 'technical/architecture/merchant-id-spaces', title: 'Tote vs wallet merchant IDs (BB / Fantasy)', description: 'Tote 255 Fantasy is the brand; wallet 1 fantasyprod is the wallet client. Never join the two id spaces.'},
  {path: 'technical/architecture/pool-controller-restart-flow', title: 'Engine pool controllers restart flow', description: 'Console → ReloadTicketsForPool → cycle data → POOL_AMENDMENT → engine restarts controllers.'},
  {path: 'technical/architecture/pool-start-sequence', title: 'Pool start sequence', description: 'Cycle Data Daemon normal start vs restart, engine pool start, commingling host and guest replication.'},
  {path: 'technical/architecture/reload-tickets-flag', title: 'reload_tickets flag', description: 'Console sets the flag; the engine clears it after handling POOL_AMENDMENT.'},
  {path: 'technical/architecture/rem-units-controller', title: 'RemUnitsController and SEP behaviour', description: 'MarketHistories, LegOfficial, remaining-unit skip rules, strategy split (is_match_kind).'},
  {path: 'technical/architecture/statsfeed-daemon', title: 'StatsFeedDaemon', description: 'How player and event stats reach stats_feed and cbtote; ToteMetricsService conditions.'},
  {path: 'technical/cbtote', title: 'cbtote', description: 'cbtote data model and domain rules.'},
  {path: 'technical/cbtote/competitor-images', title: 'Fantasy/Mido images and team keys', description: "Pick'em uses sport_event_players.image_id; team S3 key format; FOOTBALL teams use the league subcode."},
  {path: 'technical/cbtote/mvp-uses-market-metrics', title: 'MVP uses market_metrics', description: 'FantasyMvp reads and writes market_metrics; market_results is not used.'},
  {path: 'technical/cbtote/mvp-withdrawal-remaining-units', title: 'MVP withdrawal and favourite for remaining units', description: 'Withdrawn/favourite from market_snapshot, with a fallback to sport_event_competitors.'},
  {path: 'technical/conventions', title: 'Conventions', description: 'Coding conventions and quality principles.'},
  {path: 'technical/conventions/code-quality', title: 'Delete over add', description: 'Removing unnecessary code is more productive than writing new code.'},
  {path: 'technical/conventions/data-fixes', title: 'Fix duplicated data with SQL scripts', description: 'Fix duplicate data at the source with SQL scripts, not only defensive code.'},
  {path: 'technical/debugging', title: 'Debugging', description: 'Debug methods and recorded investigations.'},
  {path: 'technical/debugging/database-first-debugging', title: 'Database-first debugging', description: 'Start with database investigation before code analysis.'},
  {path: 'technical/debugging/mvp-market-metrics-2026-01', title: 'MVP market_metrics never updated (2026-01)', description: 'created_at == updated_at; SetResults never called; the two failure paths.'},
  {path: 'technical/tools', title: 'Tools', description: 'Tool-specific knowledge.'},
  {path: 'technical/tools/gitlab', title: 'GitLab conventions', description: 'Self-hosted gitlab.colossusbets.com and the gitlab-issues skill.'},
  {path: 'technical/tools/aws-cli-profile-data-warehouse-scripts', title: 'AWS profile for data-warehouse-scripts', description: 'Use --profile reporting for the AWS CLI and MCP.'},
  {path: 'technical/workflow', title: 'Workflow', description: 'Development workflow and process rules.'},
  {path: 'technical/workflow/workflow', title: 'Development workflow', description: 'Verification, debugging, local engine restriction, GitLab work items, check knowledge first.'},
  {path: 'technical/workflow/filtering-data-backend-check', title: 'Filtering data: confirm backend support', description: 'Check with the user whether filtering needs backend changes.'}
] AS c
MATCH (l:KbLibrary {name: 'colossus-bets'})
MERGE (cat:KbCategory {path: c.path})
  ON CREATE SET cat.title = c.title, cat.description = c.description
MERGE (cat)-[:KB_PART_OF]->(l);
