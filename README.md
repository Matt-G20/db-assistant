# db-assistant

An AI-powered assistant for relational databases: connect, introspect the full schema, hand that structure to an LLM for analysis, and generate SQL — with a safety layer that checks every generated query before it's allowed to run.

This is a personal learning project. I went through it once relying on generated code I didn't really understand, threw that away, and rebuilt it from scratch — by hand, line by line — so I could actually explain every part of it.

---

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Connection + full schema introspection | **done** |
| 2 | LLM analysis + agent chat | next |
| 3 | Query generation + safety layer | planned |
| 4 | Dashboard + ERD | planned |

Supported databases right now: **PostgreSQL** and **SQL Server 2019**.

---

## Why this architecture

PostgreSQL and SQL Server don't speak the same SQL dialect — the queries to list tables, columns, or keys are different for each. Instead of writing separate, disconnected code for each database, the project uses a base class that defines a *contract* (`get_tables`, `get_columns`, `get_keys`, ...), and one subclass per database that implements that contract in its own dialect.

The result: every database returns data in the **same shape**. Anything built on top of this layer (the LLM, the API, the UI) never needs to know or care which database it's talking to. Adding a new database later means writing one new class — not touching anything else.

---

## What Phase 1 does

For any connected PostgreSQL or SQL Server database, the toolkit extracts:

- **Tables** — full list of tables in the database
- **Columns** — name, data type, and nullability for every column in a table
- **Views** — name and definition of each view
- **Keys** — primary keys, and foreign keys with the table/column they reference
- **Row count** — number of rows in a table
- **Sample data** — a small, limited set of sample rows from a table (default: 5)

All of this is combined by `get_full_schema()` into one normalized structure per database — the same format regardless of which engine is behind it. This is the structure that will be handed to an LLM in Phase 2.

---

## Architecture

```
database_toolkit.py   # DatabaseToolkit base class + PostgresToolkit + SqlServerToolkit
test_toolkit.py        # runs the toolkit against a live database and prints the results
```

`DatabaseToolkit` is never used directly — it only defines the contract every database class must implement (each method raises `NotImplementedError` until a subclass overrides it). `PostgresToolkit` and `SqlServerToolkit` are the real implementations.

---

## Running it locally

Requires Python 3.11+ and access to a PostgreSQL and/or SQL Server instance.

```bash
git clone https://github.com/Matt-G20/db-assistant.git
cd db-assistant

python -m venv .venv
# Windows
.venv\Scripts\activate

pip install psycopg2-binary pyodbc python-dotenv

# create a .env file (never commit this) with:
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=testdb
# DB_USER=postgres
# DB_PASSWORD=your_password
#
# SQLSERVER_DRIVER=ODBC Driver 17 for SQL Server
# SQLSERVER_SERVER=.
# SQLSERVER_DATABASE=testdb

python test_toolkit.py
```

`.env` is gitignored. Never commit it — an earlier version of this repo did, which is why the history was rebuilt from scratch.

---

## Roadmap

- [x] `DatabaseToolkit` base class
- [x] PostgreSQL introspection (tables, columns, views, keys, row counts, samples)
- [x] SQL Server introspection (same coverage)
- [x] Unified schema output (`get_full_schema`)
- [ ] Schema → LLM context formatting
- [ ] LLM analysis (architecture explanation, issues, recommendations)
- [ ] Agent chat with tool-calling over the connected database
- [ ] Query generation
- [ ] Risk classification + execution safety layer
- [ ] Audit log
- [ ] Dashboard + ERD

---

## Notes

Progress here is incremental on purpose. Every method in `database_toolkit.py` was written and re-written by hand until I could explain what it does and why — not copied from a generated version. That's slower, but it's the point of the project.
