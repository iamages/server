from contextlib import contextmanager

from rethinkdb import RethinkDB

from .config import server_config

r = RethinkDB()

@contextmanager
def get_conn(
    host=server_config.iamages_db_host,
    port=server_config.iamages_db_port,
    user=server_config.iamages_db_user,
    password=server_config.iamages_db_pwd):
    conn = r.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db="iamages"
    )
    try:
        yield conn
    finally:
        conn.close()
