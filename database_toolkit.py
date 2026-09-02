import psycopg2
import pyodbc


class DatabaseToolkit:
    def __init__(self, connection_info):
        self.connection_info = connection_info

    def get_tables(self):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_columns(self, table_name):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_views(self):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_keys(self, table_name):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_full_schema(self):
        tables = self.get_tables()
        schema = {
            "database_type": self.__class__.__name__,
            "tables": []
        }
        for table_name in tables:
            table_info = {
                "name": table_name,
                "columns": self.get_columns(table_name),
                "keys": self.get_keys(table_name)
            }
            schema["tables"].append(table_info)
        schema["views"] = self.get_views()
        return schema


class PostgresToolkit(DatabaseToolkit):
    def get_tables(self):
        conn = psycopg2.connect(**self.connection_info)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_columns(self, table_name):
        conn = psycopg2.connect(**self.connection_info)
        cursor = conn.cursor()
        try:
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
        finally:
            cursor.close()
            conn.close()

    def get_views(self):
        conn = psycopg2.connect(**self.connection_info)
        cursor = conn.cursor()
        try:
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
        finally:
            cursor.close()
            conn.close()

    def get_keys(self, table_name):
        conn = psycopg2.connect(**self.connection_info)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
            """, (table_name,))
            primary_keys = [row[0] for row in cursor.fetchall()]

            cursor.execute("""
                SELECT kcu.column_name, ccu.table_name, ccu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'FOREIGN KEY'
            """, (table_name,))
            foreign_keys = [
                {"column": row[0], "references_table": row[1], "references_column": row[2]}
                for row in cursor.fetchall()
            ]
            return {"primary_keys": primary_keys, "foreign_keys": foreign_keys}
        finally:
            cursor.close()
            conn.close()


class SqlServerToolkit(DatabaseToolkit):
    def _connect(self):
        conn_str = (
            f"DRIVER={{{self.connection_info['driver']}}};"
            f"SERVER={self.connection_info['server']};"
            f"DATABASE={self.connection_info['database']};"
            f"Trusted_Connection=yes;"
        )
        return pyodbc.connect(conn_str)

    def get_tables(self):
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_columns(self, table_name):
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = ?
                ORDER BY ordinal_position
            """, (table_name,))
            return [
                {"name": row[0], "type": row[1], "nullable": row[2]}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()

    def get_views(self):
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT table_name, view_definition
                FROM information_schema.views
                ORDER BY table_name
            """)
            return [
                {"name": row[0], "definition": row[1]}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()

    def get_keys(self, table_name):
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                WHERE tc.TABLE_NAME = ?
                  AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            """, (table_name,))
            primary_keys = [row[0] for row in cursor.fetchall()]

            cursor.execute("""
                SELECT kcu.COLUMN_NAME, ccu.TABLE_NAME, ccu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
                  ON tc.CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
                WHERE tc.TABLE_NAME = ?
                  AND tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
            """, (table_name,))
            foreign_keys = [
                {"column": row[0], "references_table": row[1], "references_column": row[2]}
                for row in cursor.fetchall()
            ]
            return {"primary_keys": primary_keys, "foreign_keys": foreign_keys}
        finally:
            cursor.close()
            conn.close()