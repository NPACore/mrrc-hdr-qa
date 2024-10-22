#!/usr/bin/env python3
import sqlite3
# col names from 00_build_db.bash
colnames = ["AcqTime", "AcqDate", "SeriesNumber", "SubID", "iPAT", "Comments", "Operator", "Project", "SequenceName", "SequenceType", "PED_major", "TR", "TE", "Matrix", "PixelResol", "BWP", "BWPPE", "FA", "TA", "FoV"]

sql = sqlite3.connect("db.sqlite") # see schema.sql

consts = ["Project","SequenceName","iPAT","Comments","SequenceType","PED_major","TR","TE","Matrix","PixelResol","BWP","BWPPE","FA","TA","FoV"]
consts_ins_string = ",".join(consts)
val_quests = ",".join(["?" for k in consts])
sql_cmd = f"INSERT OR IGNORE INTO acq_param({consts_ins_string}) VALUES({val_quests});"
print(sql_cmd)

with open('db.txt','r') as f:
    while line := f.readline():
        vals = line.split("\t")
        d = {k:v for (k,v) in zip(colnames, vals)}
        val_array = ",".join([d[k] for k in consts])
        print(val_array)
        sql.execute(sql_cmd, val_array)
        break
        # TODO: FIX ME
        last_row_id = sql.execute("SELECT id FROM acq_param WHERE  = ?;", ())
        sql.execute("insert into acq() values () ", (last_row_id))
