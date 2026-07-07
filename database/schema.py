"""
MarketHunter

database/schema.py
"""

from __future__ import annotations

from database.connection import (
    DatabaseConnection,
)


class Schema:

    def create(
        self,
        db: DatabaseConnection,
    ) -> None:

        cur = db.cursor()

        cur.execute("""

CREATE TABLE IF NOT EXISTS signals(

id INTEGER PRIMARY KEY,

created TEXT,

symbol TEXT,

market TEXT,

strategy TEXT,

direction TEXT,

score INTEGER

)

""")

        cur.execute("""

CREATE TABLE IF NOT EXISTS trades(

id INTEGER PRIMARY KEY,

opened TEXT,

closed TEXT,

symbol TEXT,

side TEXT,

entry REAL,

exit REAL,

pnl REAL

)

""")

        cur.execute("""

CREATE TABLE IF NOT EXISTS backtests(

id INTEGER PRIMARY KEY,

created TEXT,

strategy TEXT,

winrate REAL,

profit_factor REAL,

drawdown REAL,

return_percent REAL

)

""")

        db.commit()