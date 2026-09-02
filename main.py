from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from database_toolkit import PostgresToolkit, SqlServerToolkit

app = FastAPI(title="db-assistant API")


class ConnectionRequest(BaseModel):
    db_type: str
    database: str
    host: Optional[str] = None
    port: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    driver: Optional[str] = None
    server: Optional[str] = None


def build_toolkit(req: ConnectionRequest):
    if req.db_type == "postgres":
        connection_info = {
            "host": req.host,
            "port": req.port,
            "dbname": req.database,
            "user": req.user,
            "password": req.password,
        }
        return PostgresToolkit(connection_info)
    elif req.db_type == "sqlserver":
        connection_info = {
            "driver": req.driver,
            "server": req.server,
            "database": req.database,
        }
        return SqlServerToolkit(connection_info)
    else:
        raise ValueError(f"Unsupported db_type: '{req.db_type}'. Use 'postgres' or 'sqlserver'.")


@app.get("/")
def root():
    return {"message": "db-assistant API is running"}


@app.post("/connect")
def test_connection(req: ConnectionRequest):
    try:
        toolkit = build_toolkit(req)
        toolkit.get_tables()
        return {"status": "success", "message": "Connected successfully."}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Could not connect: {str(e)}"}


@app.post("/schema")
def full_schema(req: ConnectionRequest):
    try:
        toolkit = build_toolkit(req)
        return {"status": "success", "schema": toolkit.get_full_schema()}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Failed to extract schema: {str(e)}"}