<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# AWS CLI and MCP profile for data-warehouse-scripts

**Added**: 2026-03-11
**Context**: Glue ETL dual-source planning; user specified the correct profile for this repo.
**Id**: `aws-profile-data-warehouse-scripts`

> In data-warehouse-scripts, always use the AWS profile reporting, for both the AWS CLI and the AWS MCP.

For the **data-warehouse-scripts** project, when using AWS CLI or AWS MCP:

- **Always use the `reporting` profile.**

**AWS CLI:** pass `--profile reporting` on every command, e.g.:

```bash
aws glue list-triggers --region eu-west-2 --profile reporting
```

**MCP (user-aws-mcp):** ensure the MCP server or session is configured to use the `reporting` profile when calling AWS APIs for this project (e.g. via AWS_PROFILE=reporting or equivalent in the MCP environment).
