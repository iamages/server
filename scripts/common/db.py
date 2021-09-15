from rethinkdb import RethinkDB

from .config import server_config

r = RethinkDB()

def get_conn(user: str, pwd: str, db: str):
    return r.connect(
        host=server_config.iamages_db_host,
        port=server_config.iamages_db_port,
        user=user,
        password=pwd,
        db=db
    )
