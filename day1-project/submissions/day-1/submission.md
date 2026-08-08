# Day 1 Homework Submission: Lakebase-Powered AI Support App

## Databricks App URL

[https://lakebase-support-desk-7474655808298242.aws.databricksapps.com/#tickets](https://lakebase-support-desk-7474655808298242.aws.databricksapps.com/#tickets)

## Source Code

The source code archive is included in this folder as:

`support_app_source.zip`

Public repository URL:

[https://github.com/DucDTran/databricks-lakebase-support-app.git](https://github.com/DucDTran/databricks-lakebase-support-app.git)

The repository is intended to be public for grader access.

## Evidence And Schema

Additional proof files are included in this folder:

- `evidence.md`: documents ticket creation, message posting, persisted status update, and the final data check.
- `evidence/`: contains the before/after JSON query results captured from the deployed Databricks App API.
- `lakebase_schema_ddl.sql`: contains the Lakebase DDL with primary key, foreign key, and check constraints.

## Reflection

The most difficult part was getting the Databricks App connected to Lakebase correctly, especially making sure the app service principal had the right database permissions and that the schema was created somewhere the app could write to safely. Lakebase is different from a traditional analytics table because it is designed for operational application workloads with low-latency inserts, updates, deletes, constraints, and transactional behavior, while analytics tables are usually optimized for large-scale batch reads and reporting. The next feature I would add is assignment and ownership, so each ticket can be routed to a support teammate and filtered by assignee. I would also add an activity timeline so status changes, message additions, and deletes are visible as an audit trail.
