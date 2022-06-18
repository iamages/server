from contextlib import contextmanager

from rethinkdb import RethinkDB

from .config import server_config

r = RethinkDB()
r.set_loop_type("asyncio")

class IamagesDBConnectionManager:
    def __init__(self):
        self.conn = None

    async def connect(self):
        self.conn = await r.connect(
            host=server_config.iamages_db_host,
            port=server_config.iamages_db_port,
            user=server_config.iamages_db_user,
            password=server_config.iamages_db_pwd,
            db="iamages"
        )

    async def close(self):
        await self.conn.close()

db_conn_mgr = IamagesDBConnectionManager()