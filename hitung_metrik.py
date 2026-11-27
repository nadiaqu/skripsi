
import json
import math
import sqlite3
import sys
from contextlib import closing
from itertools import combinations

import numpy as np
import pandas as pd

try:
    from scipy.stats import wilcoxon
except ImportError:
    wilcoxon = None

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "penilaian.db"
AMBANG = 4
K_LIST = (5, 10)
SISTEM = ("ddc_saja", "ddc_mbert", "mbert_saja")


def dcg(r):
    return sum(x / math.log2(i + 2) for i, x in enumerate(r))


def hitung(nilai_daftar, pool, k):
    r = nilai_daftar[:k]
    n = len(r)
    if n == 0:
        return None
    precision = sum(x >= AMBANG for x in r) / n
    mrr = next((1 / (i + 1) for i, x in enumerate(r) if x >= AMBANG), 0.0)
    ideal = dcg(sorted(pool, reverse=True)[:k])
    ndcg = dcg(r) / ideal if ideal > 0 else 0.0
    return precision, mrr, ndcg, n


def kappa_berbobot(a, b, m=5):
    """Cohen's kappa berbobot kuadratik untuk skala 1..m."""
    O = np.zeros((m, m))
    for x, y in zip(a, b):
        O[x - 1, y - 1] += 1
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    W = np.array([[(i - j) ** 2 for j in range(m)] for i in range(m)]) / (m - 1) ** 2
    den = (W * E).sum()
    return 1 - (W * O).sum() / den if den > 0 else float("nan")


def main():
    with closing(sqlite3.connect(DB_PATH)) as con:
        sesi = pd.read_sql_query("SELECT * FROM sesi", con)
        nilai = pd.read_sql_query("SELECT * FROM nilai", con)
    print(f"{len(sesi)} sesi, {len(nilai)} nilai, {sesi['rater'].nunique()} penilai\n")

    peta_nilai = {}
    for (rater, qid), g in nilai.groupby(["rater", "query_id"]):
        peta_nilai[(rater, qid)] = dict(zip(g["buku_id"], g["nilai"]))

    baris, tidak_lengkap = [], 0
    for _, s in sesi.iterrows():
        daftar = json.loads(s["daftar"])
        rating = peta_nilai.get((s["rater"], s["query_id"]), {})
        semua = {b for ids in daftar.values() for b in ids}
        if not semua or not semua.issubset(rating):
            tidak_lengkap += 1
            continue
        pool = [rating[b] for b in semua]
        for sistem in SISTEM:
            ids = daftar.get(sistem, [])
            for k in K_LIST:
                m = hitung([rating[b] for b in ids], pool, k)
                if m:
                    baris.append({"rater": s["rater"], "prodi": s["prodi"], "query_id": s["query_id"],
                                  "sistem": sistem, "k": k, "n_ditampilkan": m[3],
                                  "precision": m[0], "mrr": m[1], "ndcg": m[2]})

    print(f"Sesi lengkap dihitung: {len(sesi) - tidak_lengkap} | belum lengkap (dilewati): {tidak_lengkap}\n")
    if not baris:
        print("Belum ada sesi lengkap.")
        return

    hasil = pd.DataFrame(baris)
    hasil.to_csv("hasil_metrik.csv", index=False)
    ringkasan = (hasil.groupby(["k", "sistem"])
                 .agg(n_query=("mrr", "size"), rata2_ditampilkan=("n_ditampilkan", "mean"),
                      precision=("precision", "mean"), mrr=("mrr", "mean"), ndcg=("ndcg", "mean"))
                 .round(3))
    ringkasan.to_csv("ringkasan_metrik.csv")
    print("Ringkasan per sistem (rata-rata antar query):")
    print(ringkasan.to_string(), "\n")

    # pilihan "daftar paling relevan"
    pilihan = sesi["pilihan_terbaik"].dropna()
    if len(pilihan):
        print("Daftar yang dipilih paling relevan (persen sesi):")
        print((pilihan.value_counts(normalize=True) * 100).round(1).to_string(), "\n")

    # uji berpasangan
    if wilcoxon is not None:
        print("Uji Wilcoxon (berpasangan per query), p-value:")
        for k in K_LIST:
            for met in ("precision", "mrr", "ndcg"):
                tab = hasil[hasil.k == k].pivot(index=["rater", "query_id"], columns="sistem", values=met)
                for a, b in (("ddc_mbert", "ddc_saja"), ("ddc_mbert", "mbert_saja")):
                    if a in tab and b in tab:
                        d = (tab[a] - tab[b]).dropna()
                        if len(d) >= 5 and (d != 0).any():
                            print(f"  k={k:<2} {met:<9} {a} vs {b}: p = {wilcoxon(d).pvalue:.4f} (n={len(d)})")
        print()
    else:
        print("scipy belum terpasang: uji Wilcoxon dilewati (pip install scipy).\n")

    # kesepakatan antar penilai pada buku yang dinilai dua orang untuk query yang sama
    a_all, b_all = [], []
    for qid, g in nilai.groupby("query_id"):
        per_rater = {r: dict(zip(x["buku_id"], x["nilai"])) for r, x in g.groupby("rater")}
        for r1, r2 in combinations(per_rater, 2):
            for buku in set(per_rater[r1]) & set(per_rater[r2]):
                a_all.append(per_rater[r1][buku]); b_all.append(per_rater[r2][buku])
    if len(a_all) >= 10:
        print(f"Kesepakatan antar penilai: kappa berbobot = {kappa_berbobot(a_all, b_all):.3f} "
              f"({len(a_all)} pasang nilai)")
    else:
        print("Belum cukup pasangan nilai antar penilai untuk menghitung kappa "
              "(satu query perlu dinilai oleh dua orang).")


if __name__ == "__main__":
    main()
