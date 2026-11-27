
import hashlib
import json
import os

import numpy as np
import pandas as pd

try:
    from rapidfuzz import fuzz, process
    ADA_RAPIDFUZZ = True
except ImportError:
    ADA_RAPIDFUZZ = False

SISTEM = ("ddc_saja", "ddc_mbert", "mbert_saja")
NAMA_SISTEM = {"ddc_saja": "DDC saja", "ddc_mbert": "DDC + mBERT", "mbert_saja": "mBERT saja"}

URUTAN_DDC_SAJA = "kedekatan"

def muat_data(data_csv, vektor_npy):
    df = pd.read_csv(data_csv, dtype=str).reset_index(drop=True)
    df["ddc_number"] = df["ddc_number"].fillna("").str.strip()
    df["full_title"] = df["full_title"].fillna("").astype(str)
    df["judul_lc"] = df["full_title"].str.lower()

    V = np.load(vektor_npy).astype(np.float32)
    assert len(df) == len(V), f"Jumlah baris CSV ({len(df)}) tidak sama dengan jumlah vektor ({len(V)})"

    meta_path = vektor_npy.replace(".npy", ".meta.json")
    if os.path.exists(meta_path):
        sidik = hashlib.md5("\n".join(df["oai_identifier"]).encode()).hexdigest()[:8]
        with open(meta_path) as fh:
            assert json.load(fh)["fingerprint"] == sidik, (
                "buku.csv tidak cocok dengan file vektor. Jalankan ulang 02_vectorization.ipynb."
            )

    V /= np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-12)
    id_ke_idx = {oid: i for i, oid in enumerate(df["oai_identifier"])}
    return df, V, df["judul_lc"].tolist(), id_ke_idx



def cari_judul(kata, df, daftar_lc, maks=20):
    kata = kata.lower().strip()
    if len(kata) < 2:
        return []

    persis = df.index[df["judul_lc"].str.contains(kata, regex=False)].tolist()
    persis.sort(key=lambda i: len(daftar_lc[i]))       # judul yang lebih pendek (lebih dekat) di atas
    hasil = persis[:maks]

    if len(hasil) < maks and ADA_RAPIDFUZZ:
        mirip = process.extract(kata, daftar_lc, scorer=fuzz.WRatio, limit=maks * 3, score_cutoff=75)
        sudah = set(hasil)
        for _, _, i in mirip:
            if i not in sudah:
                hasil.append(i)
                sudah.add(i)
            if len(hasil) >= maks:
                break
    return hasil


def ada_desimal(ddc):
    return "." in ddc


def potong_satu_digit(ddc):
    return ddc[:-1].rstrip(".")


def _seed(teks):
    return int(hashlib.md5(str(teks).encode()).hexdigest()[:8], 16)


def _telusuri(idx, df, V, k, urutkan):
    """Putaran 0: nomor buku (awalan). Selama list < k dan masih ada desimal: naik satu digit.
    urutkan(kandidat, skor, awalan) -> posisi urutan kandidat pada putaran itu."""
    ddc = df.at[idx, "ddc_number"]
    if not ddc:
        return [], []

    q = V[idx]
    kolom = df["ddc_number"]
    terpakai = np.zeros(len(df), dtype=bool)
    terpakai[idx] = True
    hasil, jejak, putaran = [], [], 0

    while True:
        cocok = kolom.str.startswith(ddc).to_numpy(dtype=bool)
        kandidat = np.flatnonzero(cocok & ~terpakai)
        if kandidat.size:
            skor = V[kandidat] @ q
            for j in urutkan(kandidat, skor, ddc):
                hasil.append({"idx": int(kandidat[j]), "skor": float(skor[j]),
                              "awalan": ddc, "putaran": putaran})
            terpakai[kandidat] = True
        jejak.append({"Putaran": putaran, "Awalan DDC": ddc,
                      "Kandidat baru": int(kandidat.size), "Isi list": len(hasil)})

        if len(hasil) >= k or not ada_desimal(ddc):
            break
        ddc = potong_satu_digit(ddc)
        putaran += 1

    return hasil[:k], jejak


def rekomendasi_ddc_mbert(idx, df, V, k=10):
    return _telusuri(idx, df, V, k, lambda kand, skor, awalan: np.argsort(-skor, kind="stable"))


def rekomendasi_ddc_saja(idx, df, V, k=10, urutan=None):
    urutan = urutan or URUTAN_DDC_SAJA
    rng = np.random.default_rng(_seed(df.at[idx, "oai_identifier"]))
    panjang = df["ddc_number"].str.len().to_numpy()

    def urutkan(kand, skor, awalan):
        acak = rng.random(len(kand))
        if urutan == "acak":
            return np.argsort(acak, kind="stable")
        ekstra = panjang[kand] - len(awalan)
        return np.lexsort((acak, ekstra))

    return _telusuri(idx, df, V, k, urutkan)


def rekomendasi_mbert_saja(idx, V, k=10):
    skor = V @ V[idx]
    skor[idx] = -np.inf
    k = min(k, len(V) - 1)
    if k <= 0:
        return []
    atas = np.argpartition(-skor, k - 1)[:k]
    atas = atas[np.argsort(-skor[atas], kind="stable")]
    return [{"idx": int(i), "skor": float(skor[i]), "awalan": "", "putaran": 0} for i in atas]


def hitung_semua(idx, df, V, k=10, sistem=SISTEM):
    """Mengembalikan ({nama_sistem: daftar_hasil}, jejak_ddc_mbert)."""
    daftar, jejak = {}, []
    if "ddc_saja" in sistem:
        daftar["ddc_saja"], _ = rekomendasi_ddc_saja(idx, df, V, k)
    if "ddc_mbert" in sistem:
        daftar["ddc_mbert"], jejak = rekomendasi_ddc_mbert(idx, df, V, k)
    if "mbert_saja" in sistem:
        daftar["mbert_saja"] = rekomendasi_mbert_saja(idx, V, k)
    return daftar, jejak


def acak_susunan(rater, query_id):
    """Urutan sistem pada Daftar 1, 2, 3. Tetap untuk pasangan (penilai, buku) yang sama."""
    rng = np.random.default_rng(_seed(f"{rater}|{query_id}|susunan"))
    s = list(SISTEM)
    rng.shuffle(s)
    return s
