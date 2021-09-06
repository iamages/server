from contextlib import contextmanager

from rethinkdb import RethinkDB

from .config import server_config

r = RethinkDB()

@contextmanager
def get_conn():
    conn =  r.connect(
        host=server_config.iamages_db_host,
        port=server_config.iamages_db_port,
        user=server_config.iamages_db_user,
        password=server_config.iamages_db_pwd,
        db="iamages"
    )
    try:
        yield conn
    finally:
        conn.close()
