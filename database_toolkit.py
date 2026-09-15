from contextlib import contextmanager

import psycopg2
from psycopg2 import sql
import pyodbc


class DatabaseToolkit:
    def __init__(self, connection_info):
        self.connection_info = connection_info

    def _connect(self):
        raise NotImplementedError("This method should be implemented by subclasses.")

    @contextmanager
    def _cursor(self, conn=None):
        """Yield a cursor for a query.

        If the caller didn't pass a connection, one is opened here and
        closed here when the block exits (even if cursor creation or the
        query itself raises). If the caller passed a connection (as
        get_full_schema does, to reuse one connection across many calls),
        it is left open for the caller to close.
        """
        owns_conn = conn is None
        conn = conn or self._connect()
        try:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
        finally:
            if owns_conn:
                conn.close()

    def get_tables(self, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_columns(self, table_name, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_views(self, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_keys(self, table_name, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_row_count(self, table_name, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_sample(self, table_name, limit=5, conn=None):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_full_schema(self):
        # Open a single connection and thread it through every call below
        # instead of letting each get_* method open its own. Without this,
        # a database with N tables opened 3N+1 separate connections just to
        # build one schema snapshot.
        conn = self._connect()
        try:
            tables = self.get_tables(conn=conn)
            schema = {
                "database_type": self.__class__.__name__,
                "tables": []
            }
            for table_name in tables:
                table_info = {
                    "name": table_name,
                    "columns": self.get_columns(table_name, conn=conn),
                    "keys": self.get_keys(table_name, conn=conn),
                    "row_count": self.get_row_count(table_name, conn=conn)
                }
                schema["tables"].append(table_info)
            schema["views"] = self.get_views(conn=conn)
            return schema
        finally:
            conn.close()


class PostgresToolkit(DatabaseToolkit):
    SCHEMA = "public"

    def _connect(self):
        return psycopg2.connect(**self.connection_info)

    def get_tables(self, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table_name, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            return [
                {"name": row[0], "type": row[1], "nullable": row[2]}
                for row in cursor.fetchall()
            ]

    def get_views(self, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT table_name, view_definition
                FROM information_schema.views
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            return [
                {"name": row[0], "definition": row[1]}
                for row in cursor.fetchall()
            ]

    def get_keys(self, table_name, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position
            """, (table_name,))
            primary_keys = [row[0] for row in cursor.fetchall()]

            # Note: joining key_column_usage/constraint_column_usage on
            # constraint_name alone produces a cartesian product for
            # composite (multi-column) foreign keys, silently pairing up
            # unrelated columns. Using pg_constraint's conkey/confkey
            # arrays (zipped positionally via unnest) pairs each local
            # column with its correct referenced column instead.
            cursor.execute("""
                SELECT
                    parent_att.attname AS column_name,
                    referenced_cl.relname AS references_table,
                    referenced_att.attname AS references_column
                FROM pg_constraint con
                JOIN pg_class cl ON cl.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = cl.relnamespace
                JOIN pg_class referenced_cl ON referenced_cl.oid = con.confrelid
                CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
                    WITH ORDINALITY AS cols(parent_attnum, referenced_attnum, ord)
                JOIN pg_attribute parent_att
                    ON parent_att.attrelid = con.conrelid
                   AND parent_att.attnum = cols.parent_attnum
                JOIN pg_attribute referenced_att
                    ON referenced_att.attrelid = con.confrelid
                   AND referenced_att.attnum = cols.referenced_attnum
                WHERE con.contype = 'f'
                  AND ns.nspname = 'public'
                  AND cl.relname = %s
                ORDER BY cols.ord
            """, (table_name,))
            foreign_keys = [
                {"column": row[0], "references_table": row[1], "references_column": row[2]}
                for row in cursor.fetchall()
            ]
            return {"primary_keys": primary_keys, "foreign_keys": foreign_keys}

    def get_row_count(self, table_name, conn=None):
        with self._cursor(conn) as cursor:
            query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(self.SCHEMA, table_name)
            )
            cursor.execute(query)
            return cursor.fetchone()[0]

    def get_sample(self, table_name, limit=5, conn=None):
        limit = int(limit)
        with self._cursor(conn) as cursor:
            query = sql.SQL("SELECT * FROM {} LIMIT %s").format(
                sql.Identifier(self.SCHEMA, table_name)
            )
            cursor.execute(query, (limit,))
            column_names = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(column_names, row)) for row in rows]


class SqlServerToolkit(DatabaseToolkit):
    # Fallback schema used only when a caller passes a bare (unqualified)
    # table name directly to get_columns/get_keys/get_row_count/get_sample
    # instead of the "schema.table" form get_tables() returns. SQL Server
    # databases routinely spread tables across multiple schemas (e.g. the
    # AdventureWorks sample uses Sales, Person, Production, ...), so -
    # unlike PostgresToolkit, which only ever deals with 'public' -
    # get_tables() here returns every schema, qualified, rather than
    # silently hiding everything outside one hardcoded schema.
    SCHEMA = "dbo"

    @staticmethod
    def _quote_identifier(name):
        return "[" + name.replace("]", "]]") + "]"

    @classmethod
    def _split_schema_table(cls, table_name):
        if "." in table_name:
            schema, _, name = table_name.partition(".")
            return schema, name
        return cls.SCHEMA, table_name

    @staticmethod
    def _escape_conn_value(value):
        # ODBC connection string values containing ';', '{', '}', or
        # spaces must be brace-quoted, with any literal '}' doubled.
        # Without this, a ';' in e.g. a password would inject extra,
        # attacker-controlled connection-string keywords.
        return "{" + str(value).replace("}", "}}") + "}"

    def _connect(self):
        esc = self._escape_conn_value
        conn_str = (
            f"DRIVER={esc(self.connection_info['driver'])};"
            f"SERVER={esc(self.connection_info['server'])};"
            f"DATABASE={esc(self.connection_info['database'])};"
        )
        user = self.connection_info.get("user")
        password = self.connection_info.get("password")
        if user:
            # password may legitimately be omitted/None; without the
            # `or ""` this would render as the literal text "PWD=None;"
            conn_str += f"UID={esc(user)};PWD={esc(password or '')};"
        else:
            conn_str += "Trusted_Connection=yes;"
        return pyodbc.connect(conn_str)

    def get_tables(self, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            return [f"{row[0]}.{row[1]}" for row in cursor.fetchall()]

    def get_columns(self, table_name, conn=None):
        schema, name = self._split_schema_table(table_name)
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """, (schema, name))
            return [
                {"name": row[0], "type": row[1], "nullable": row[2]}
                for row in cursor.fetchall()
            ]

    def get_views(self, conn=None):
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION
                FROM INFORMATION_SCHEMA.VIEWS
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            return [
                {"name": f"{row[0]}.{row[1]}", "definition": row[2]}
                for row in cursor.fetchall()
            ]

    def get_keys(self, table_name, conn=None):
        schema, name = self._split_schema_table(table_name)
        with self._cursor(conn) as cursor:
            cursor.execute("""
                SELECT c.name AS column_name
                FROM sys.indexes i
                JOIN sys.index_columns ic
                  ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                JOIN sys.columns c
                  ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                JOIN sys.tables t ON t.object_id = i.object_id
                JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE i.is_primary_key = 1
                  AND s.name = ?
                  AND t.name = ?
                ORDER BY ic.key_ordinal
            """, (schema, name))
            primary_keys = [row[0] for row in cursor.fetchall()]

            # sys.foreign_key_columns already stores one row per column
            # pair (correctly matched via constraint_column_id), unlike
            # the INFORMATION_SCHEMA key_column_usage/constraint_column_usage
            # join which cartesian-products composite foreign keys.
            cursor.execute("""
                SELECT
                    pc.name AS column_name,
                    rs.name AS references_schema,
                    rt.name AS references_table,
                    rc.name AS references_column
                FROM sys.foreign_key_columns fkc
                JOIN sys.tables t ON fkc.parent_object_id = t.object_id
                JOIN sys.schemas s ON s.schema_id = t.schema_id
                JOIN sys.columns pc
                  ON fkc.parent_object_id = pc.object_id
                 AND fkc.parent_column_id = pc.column_id
                JOIN sys.tables rt ON fkc.referenced_object_id = rt.object_id
                JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
                JOIN sys.columns rc
                  ON fkc.referenced_object_id = rc.object_id
                 AND fkc.referenced_column_id = rc.column_id
                WHERE s.name = ?
                  AND t.name = ?
                ORDER BY fkc.constraint_column_id
            """, (schema, name))
            foreign_keys = [
                {
                    "column": row[0],
                    "references_table": f"{row[1]}.{row[2]}",
                    "references_column": row[3],
                }
                for row in cursor.fetchall()
            ]
            return {"primary_keys": primary_keys, "foreign_keys": foreign_keys}

    def get_row_count(self, table_name, conn=None):
        schema, name = self._split_schema_table(table_name)
        with self._cursor(conn) as cursor:
            quoted = f"{self._quote_identifier(schema)}.{self._quote_identifier(name)}"
            cursor.execute(f"SELECT COUNT(*) FROM {quoted};")
            return cursor.fetchone()[0]

    def get_sample(self, table_name, limit=5, conn=None):
        limit = int(limit)
        schema, name = self._split_schema_table(table_name)
        with self._cursor(conn) as cursor:
            quoted = f"{self._quote_identifier(schema)}.{self._quote_identifier(name)}"
            cursor.execute(f"SELECT TOP (?) * FROM {quoted};", (limit,))
            column_names = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(column_names, row)) for row in rows]
