import json
import sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = "penilaian.db"

SKEMA = """
CREATE TABLE IF NOT EXISTS sesi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rater TEXT NOT NULL,
    prodi TEXT,
    query_id TEXT NOT NULL,
    query_judul TEXT,
    k INTEGER NOT NULL,
    susunan TEXT NOT NULL,          -- JSON: {"Daftar 1": "ddc_mbert", ...}
    daftar TEXT NOT NULL,           -- JSON: {"ddc_saja": [id buku urut], ...}
    pilihan_terbaik TEXT,           -- nama sistem, atau "sama"
    waktu TEXT NOT NULL,
    UNIQUE (rater, query_id)
);
CREATE TABLE IF NOT EXISTS nilai (
    rater TEXT NOT NULL,
    query_id TEXT NOT NULL,
    buku_id TEXT NOT NULL,
    nilai INTEGER NOT NULL CHECK (nilai BETWEEN 1 AND 5),
    waktu TEXT NOT NULL,
    PRIMARY KEY (rater, query_id, buku_id)
);
"""


def _koneksi():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def _sekarang():
    return datetime.now().isoformat(timespec="seconds")


def siapkan():
    with closing(_koneksi()) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SKEMA)
        con.commit()


def _ke_sesi(row):
    if row is None:
        return None
    d = dict(row)
    d["susunan"] = json.loads(d["susunan"])
    d["daftar"] = json.loads(d["daftar"])
    return d


def ambil_sesi(rater, query_id):
    with closing(_koneksi()) as con:
        row = con.execute("SELECT * FROM sesi WHERE rater=? AND query_id=?", (rater, query_id)).fetchone()
    return _ke_sesi(row)


def buat_sesi(rater, prodi, query_id, query_judul, k, susunan, daftar):
    with closing(_koneksi()) as con, con:
        con.execute(
            "INSERT OR IGNORE INTO sesi (rater, prodi, query_id, query_judul, k, susunan, daftar, waktu) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rater, prodi, query_id, query_judul, k, json.dumps(susunan), json.dumps(daftar), _sekarang()),
        )
    return ambil_sesi(rater, query_id)


def simpan_nilai(rater, query_id, buku_id, nilai):
    with closing(_koneksi()) as con, con:
        con.execute(
            "INSERT INTO nilai (rater, query_id, buku_id, nilai, waktu) VALUES (?,?,?,?,?) "
            "ON CONFLICT(rater, query_id, buku_id) DO UPDATE SET nilai=excluded.nilai, waktu=excluded.waktu",
            (rater, query_id, buku_id, int(nilai), _sekarang()),
        )


def ambil_nilai(rater, query_id):
    with closing(_koneksi()) as con:
        rows = con.execute("SELECT buku_id, nilai FROM nilai WHERE rater=? AND query_id=?",
                           (rater, query_id)).fetchall()
    return {r["buku_id"]: r["nilai"] for r in rows}


def simpan_pilihan(rater, query_id, sistem):
    with closing(_koneksi()) as con, con:
        con.execute("UPDATE sesi SET pilihan_terbaik=? WHERE rater=? AND query_id=?", (sistem, rater, query_id))
