import sqlite3
from datetime import datetime, timedelta

# Create and in-memory SQLite database
test_db = sqlite3.connect(":memory:")

# Create tables based off of the original schema
test_db.execute("""
                CREATE TABLE acq (
                    param_id INTEGER,
                    AcqTime TEXT,
                    AcqDate TEXT,
                    SeriesNumber TEXT,
                    SubID TEXT,
                    Operator TEXT
                );
                """)

test_db.execute("""
                CREATE TABLE acq_param (
                    is_ideal TIMESTAMP,
                    Project TEXT,
                    SequenceName TEXT,
                    iPAT TEXT,
                    Phase TEXT,
                    Comments TEXT,
                    SequenceType TEXT,
                    PED_major TEXT,
                    TR TEXT,
                    TE TEXT,
                    Matrix TEXT,
                    PixelResol TEXT,
                    BWP TEXT,
                    BWPPE TEXT,
                    FA TEXT,
                    TA TEXT,
                    FoV TEXT
                );
                """)

# Sample dates for testing
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
day_before_yesterday = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

# Insert test data into the acq table
test_data = [
        (1, "10:00", day_before_yesterday, "001", "SUB1", "OP1"),
        (2, "11:00", yesterday, "002", "SUB2", "OP2"),
        (3, "12:00", today, "003", "SUB3", "OP3"),
]

test_db.executemany("INSERT INTO acq (param_id, AcqTime, AcqDate, SeriesNumber, SubID, Operator) VALUES (?, ?, ?, ?, ?, ?)", test_data)
test_db.commit()

# Define the DBQuery class with find_acquisitions_since function
from typing import Optional

class DBQuery:
    def __init__(self, sql=None):
        self.sql = sql if sql else sqlite3.connect("db.sqlite")

    def find_acquisitions_since(self, since_date: Optional[str] = None):
        if since_date is None:
            since_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        query = "SELECT * FROM acq WHERE AcqDate > ?"
        cur = self.sql.execute(query, (since_date,))
        return cur.fetchall()

# Instantiate DBQuery with test database
db_query = DBQuery(sql=test_db)

# Test the function with different data inputs
print("Results since yesterday:", db_query.find_acquisitions_since(yesterday))
print("Results since today:", db_query.find_acquisitions_since(today))
print("Results since 2000-01-01:", db_query.find_acquisitions_since("2000-01-01"))
print("Results with default (since yesterday):", db_query.find_acquisitions_since())

# CLose the test database
test_db.close()
