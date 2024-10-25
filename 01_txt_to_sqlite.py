#!/usr/bin/env python3
"""
convert db.txt into a sqlite database
"""
import sqlite3
import re

# CSA col names from 00_build_db.bash not in taglist.txt
colnames = ["Phase", "iPAT"]
with open('taglist.txt','r') as f:
    tag_colnames = [line.split("\t")[0]
                    for line in f.readlines()
                    if not re.search("^name|^#", line)]
colnames += tag_colnames
colnames += ['filename'] # final file name column also not in taglist.txt (not a tag)

sql = sqlite3.connect("db.sqlite") # see schema.sql

consts = ["Project","SequenceName","iPAT","Comments","SequenceType","PED_major","TR","TE","Matrix","PixelResol","BWP","BWPPE","FA","TA","FoV"]
consts_ins_string = ",".join(consts)
val_quests = ",".join(["?" for k in consts])
sql_cmd = f"INSERT OR IGNORE INTO acq_param({consts_ins_string}) VALUES({val_quests});"
print(sql_cmd)

with open('db.txt','r') as f:
    while line := f.readline():
        vals = line.split("\t")
        d = dict(zip(colnames, vals))
        val_array = [d[k] for k in consts]
        print(val_array)
        sql.execute(sql_cmd, val_array)
        continue
        # TODO: FIX ME
        last_row_id = sql.execute("SELECT id FROM acq_param WHERE  = ?;", ())
        sql.execute("insert into acq() values () ", (last_row_id))
sql.commit()
