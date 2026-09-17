import os
import json
from dotenv import load_dotenv
from database_toolkit import PostgresToolkit, SqlServerToolkit

load_dotenv()

postgres_info = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

pg = PostgresToolkit(postgres_info)
print(json.dumps(pg.get_full_schema(), indent=2))

sqlserver_info = {
    "driver": os.getenv("SQLSERVER_DRIVER"),
    "server": os.getenv("SQLSERVER_SERVER"),
    "database": os.getenv("SQLSERVER_DATABASE"),
    "user": os.getenv("SQLSERVER_USER"),
    "password": os.getenv("SQLSERVER_PASSWORD")
}

ss = SqlServerToolkit(sqlserver_info)
print(json.dumps(ss.get_full_schema(), indent=2))