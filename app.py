import html

import pandas as pd
import streamlit as st

import core
import penyimpanan

DATA_CSV = "buku.csv"
VEKTOR_NPY = "vektor_buku_f16.npy"
K_UJI = 10
TAMPILKAN_SUBJEK_UJI = True

st.set_page_config(page_title="Rekomendasi Buku", page_icon="📗", layout="wide")
MODE_UJI = st.query_params.get("mode") == "uji"

st.markdown(
    """
    <style>
    .header-bar {background:#1E5631; padding:12px 22px; border-radius:8px; margin-bottom:14px;}
    .header-bar h1 {color:#FFFFFF; font-size:1.4rem; margin:0; padding:0;}
    .header-bar p {color:#CFE8D3; margin:2px 0 0 0; font-size:0.85rem;}
    .ddc-badge {background:#EAF4EA; color:#1E5631; border:1px solid #B7D8BC; border-radius:4px;
                padding:1px 8px; font-size:0.85rem; font-family:monospace;}
    .kartu-judul {font-weight:600; margin-bottom:2px;}
    .kartu-info {font-size:0.85rem; opacity:0.8;}
    .kecil {font-size:0.8rem; opacity:0.7;}
    .detail-judul {font-size:1.3rem; font-weight:700; margin-bottom:4px;}
    </style>
    """,
    unsafe_allow_html=True,
)
judul_header = "Penilaian Rekomendasi Buku" if MODE_UJI else "Rekomendasi Buku Perpustakaan"
sub_header = ("Bantu menilai seberapa relevan rekomendasi yang diberikan" if MODE_UJI
              else "Prototipe: penelusuran hierarki DDC dan pengurutan mBERT")
st.markdown(f"<div class='header-bar'><h1>{judul_header}</h1><p>{sub_header}</p></div>", unsafe_allow_html=True)


@st.cache_resource
def muat():
    return core.muat_data(DATA_CSV, VEKTOR_NPY)


@st.cache_resource
def siapkan_db():
    penyimpanan.siapkan()
    return True


@st.cache_data(show_spinner=False)
def cari(kata, maks):
    return core.cari_judul(kata, df, daftar_lc, maks)


df, V, daftar_lc, id_ke_idx = muat()
if MODE_UJI:
    siapkan_db()

S = st.session_state
for nama, awal in dict(halaman="awal", kata="", buku=None, maks=20, nilai={}, sesi=None).items():
    if nama not in S:
        S[nama] = awal


def teks(i, kolom, maks=None):
    if kolom not in df.columns:
        return ""
    v = df.at[i, kolom]
    if pd.isna(v):
        return ""
    v = str(v).strip()
    return v[:maks] + "…" if maks and len(v) > maks else v


def kartu_html(i, rank=None, ddc=False, subjek=False, ekstra=""):
    nomor = f"<span class='kecil'>{rank}.</span> " if rank else ""
    bagian = [f"<div class='kartu-judul'>{nomor}{html.escape(teks(i, 'full_title'))}</div>"]
    info = " · ".join(html.escape(x) for x in [teks(i, "author_main"), teks(i, "publisher"),
                                                teks(i, "date_publication"), teks(i, "language")] if x)
    if info:
        bagian.append(f"<div class='kartu-info'>{info}</div>")
    if subjek and teks(i, "subject"):
        bagian.append(f"<div class='kartu-info'>Subjek: {html.escape(teks(i, 'subject', 110))}</div>")
    if ddc and teks(i, "ddc_number"):
        bagian.append(f"<span class='ddc-badge'>DDC {html.escape(teks(i, 'ddc_number'))}</span>")
    if ekstra:
        bagian.append(f" <span class='kecil'>{ekstra}</span>")
    return "".join(bagian)


def asal_teks(sistem, h):
    if sistem == "mbert_saja":
        return "seluruh koleksi"
    return "nomor asal" if h["putaran"] == 0 else f"naik ke {html.escape(h['awalan'])}"


def ke_hasil(kata):
    S["kata"] = kata
    S["halaman"] = "hasil"
    S["maks"] = 20


def pilih_buku(i):
    S["buku"] = i
    S["halaman"] = "detail"
    S["sesi"] = None
    S["nilai"] = {}


def kembali():
    S["halaman"] = "hasil" if S["kata"] else "awal"


def tambah_maks():
    S["maks"] = S["maks"] + 20


def form_cari(sejajar):
    with st.form("form_cari"):
        if sejajar:
            c1, c2 = st.columns([6, 1])
            kata = c1.text_input("Cari judul buku", value=S["kata"], placeholder="contoh: sql pocket guide",
                                 label_visibility="collapsed")
            kirim = c2.form_submit_button("Cari")
        else:
            kata = st.text_input("Cari judul buku", value=S["kata"], placeholder="contoh: sql pocket guide",
                                 label_visibility="collapsed")
            kirim = st.form_submit_button("Cari")
    if kirim and kata.strip():
        ke_hasil(kata.strip())
        st.rerun()


def bar_atas():
    kiri, kanan = st.columns([5, 2])
    with kanan:
        if MODE_UJI:
            st.caption(f"Penilai: {S['rater']['kode']} · {S['rater']['prodi']}")
        else:
            st.toggle("Bandingkan 3 algoritma", key="tiga_mode")
    return kiri


if MODE_UJI and "rater" not in S:
    st.markdown(
        "Terima kasih sudah bersedia menilai. Caranya: **pilih satu buku dari bidangmu**, lihat tiga daftar "
        "rekomendasi, lalu beri nilai 1 sampai 5 untuk setiap buku. Tidak ada jawaban benar atau salah."
    )
    with st.form("form_penilai"):
        kode = st.text_input("Kode penilai (nama atau inisial)")
        prodi = st.text_input("Program studi")
        mulai = st.form_submit_button("Mulai")
    if mulai:
        if kode.strip() and prodi.strip():
            S["rater"] = {"kode": kode.strip(), "prodi": prodi.strip()}
            st.rerun()
        else:
            st.warning("Isi kode penilai dan program studi.")
    st.stop()


def kotak_detail(i):
    with st.container(border=True):
        st.caption("Buku yang dipilih")
        st.markdown(f"<div class='detail-judul'>{html.escape(teks(i, 'full_title'))}</div>", unsafe_allow_html=True)
        rincian = [("Pengarang", "author_main"), ("Penerbit", "publisher"), ("Tahun", "date_publication"),
                   ("Edisi", "edition"), ("Bahasa", "language"), ("Subjek", "subject")]
        if not MODE_UJI:
            rincian += [("Nomor DDC", "ddc_number"), ("Nomor panggil", "call_number_ddc")]
        for label, kolom in rincian:
            nilai = teks(i, kolom, 200)
            if nilai:
                st.markdown(f"<div class='kartu-info'><b>{label}:</b> {html.escape(nilai)}</div>", unsafe_allow_html=True)

def daftar_demo(hasil, sistem):
    if not hasil:
        st.info("Tidak ada buku yang ditemukan.")
    for n, h in enumerate(hasil, 1):
        with st.container(border=True):
            ekstra = f"skor {h['skor']:.3f} · {asal_teks(sistem, h)}"
            st.markdown(kartu_html(h["idx"], rank=n, ddc=True, ekstra=ekstra), unsafe_allow_html=True)


def halaman_demo(i):
    k = st.slider("Jumlah rekomendasi", min_value=3, max_value=10, value=10)
    if not S.get("tiga_mode", False):
        daftar, jejak = core.hitung_semua(i, df, V, k, sistem=("ddc_mbert",))
        st.subheader("Rekomendasi")
        daftar_demo(daftar["ddc_mbert"], "ddc_mbert")
        if 0 < len(daftar["ddc_mbert"]) < k:
            st.info(f"Hanya {len(daftar['ddc_mbert'])} buku yang ditampilkan karena penelusuran berhenti "
                    "pada batas tanda desimal.")
    else:
        daftar, jejak = core.hitung_semua(i, df, V, k)
        kolom = st.columns(3)
        for kol, sistem in zip(kolom, core.SISTEM):
            with kol:
                st.markdown(f"**{core.NAMA_SISTEM[sistem]}**")
                with st.container(height=560):
                    daftar_demo(daftar[sistem], sistem)
    with st.expander("Jejak penelusuran (DDC + mBERT)"):
        st.dataframe(pd.DataFrame(jejak), hide_index=True, use_container_width=True)


def simpan_nilai_cb(buku_id, kunci):
    nilai = S.get(kunci)
    if nilai is None:
        return
    S["nilai"][buku_id] = int(nilai)
    penyimpanan.simpan_nilai(S["rater"]["kode"], S["sesi"]["query_id"], buku_id, int(nilai))


def simpan_terbaik_cb(kunci):
    label = S.get(kunci)
    if label is None:
        return
    sistem = "sama" if label == "Sama saja" else S["sesi"]["susunan"][label]
    penyimpanan.simpan_pilihan(S["rater"]["kode"], S["sesi"]["query_id"], sistem)
    S["sesi"]["pilihan_terbaik"] = sistem


def kartu_uji(rank, buku_id, label):
    j = id_ke_idx[buku_id]
    with st.container(border=True):
        st.markdown(kartu_html(j, rank=rank, ddc=False, subjek=TAMPILKAN_SUBJEK_UJI), unsafe_allow_html=True)
        kunci = f"n_{label}_{buku_id}"
        tersimpan = S["nilai"].get(buku_id)
        # buku yang sama di daftar lain memakai nilai yang sama
        if tersimpan is not None and S.get(kunci) != tersimpan:
            S[kunci] = tersimpan
        st.radio("Nilai", [1, 2, 3, 4, 5], index=None, horizontal=True, key=kunci,
                 label_visibility="collapsed", on_change=simpan_nilai_cb, args=(buku_id, kunci))


def halaman_uji(i):
    rater = S["rater"]["kode"]
    qid = df.at[i, "oai_identifier"]

    if S["sesi"] is None or S["sesi"]["query_id"] != qid:
        sesi = penyimpanan.ambil_sesi(rater, qid)
        if sesi is None:
            daftar, _ = core.hitung_semua(i, df, V, K_UJI)
            susunan = {f"Daftar {n + 1}": s for n, s in enumerate(core.acak_susunan(rater, qid))}
            ids = {s: [df.at[h["idx"], "oai_identifier"] for h in daftar[s]] for s in daftar}
            sesi = penyimpanan.buat_sesi(rater, S["rater"]["prodi"], qid, df.at[i, "full_title"],
                                         K_UJI, susunan, ids)
        S["sesi"] = sesi
        S["nilai"] = penyimpanan.ambil_nilai(rater, qid)
    sesi = S["sesi"]

    semua_id = sorted({b for ids in sesi["daftar"].values() for b in ids})
    if not semua_id:
        st.info("Tidak ada rekomendasi untuk buku ini. Silakan pilih buku lain.")
        return

    st.markdown(
        "**Seberapa relevan buku ini bagi orang yang sedang mencari buku di atas?** "
        "Beri nilai pada setiap buku: 1 = tidak relevan, 3 = cukup relevan, 5 = sangat relevan. "
        "Buku yang sama di beberapa daftar hanya perlu dinilai sekali."
    )
    sudah = sum(b in S["nilai"] for b in semua_id)
    st.progress(sudah / len(semua_id))
    st.caption(f"Sudah dinilai {sudah} dari {len(semua_id)} buku")

    kolom = st.columns(3)
    for n, kol in enumerate(kolom, 1):
        label = f"Daftar {n}"
        sistem = sesi["susunan"][label]
        with kol:
            st.markdown(f"**{label}**")
            with st.container(height=560):
                for r, buku_id in enumerate(sesi["daftar"][sistem], 1):
                    kartu_uji(r, buku_id, label)

    if sudah == len(semua_id):
        st.success("Semua buku sudah dinilai. Satu pertanyaan terakhir, lalu kamu boleh memilih buku lain.")
    opsi = ["Daftar 1", "Daftar 2", "Daftar 3", "Sama saja"]
    tersimpan = sesi.get("pilihan_terbaik")
    balik = {sistem: label for label, sistem in sesi["susunan"].items()}
    awal = 3 if tersimpan == "sama" else (opsi.index(balik[tersimpan]) if tersimpan in balik else None)
    kunci = f"terbaik_{qid}"
    st.radio("Menurutmu, daftar mana yang paling relevan secara keseluruhan?", opsi, index=awal,
             horizontal=True, key=kunci, on_change=simpan_terbaik_cb, args=(kunci,))


if S["halaman"] == "awal":
    bar_atas()
    st.write("")
    _, tengah, _ = st.columns([1, 3, 1])
    with tengah:
        st.markdown("<h3 style='text-align:center'>Cari buku yang ingin kamu jadikan acuan</h3>",
                    unsafe_allow_html=True)
        form_cari(sejajar=False)

elif S["halaman"] == "hasil":
    bar_atas()
    form_cari(sejajar=True)
    hasil = cari(S["kata"], S["maks"])
    if not hasil:
        st.warning("Judul tidak ditemukan. Coba kata kunci lain.")
    else:
        st.caption(f"{len(hasil)} hasil untuk “{S['kata']}”")
        for i in hasil:
            with st.container(border=True):
                c1, c2 = st.columns([8, 1])
                c1.markdown(kartu_html(i, ddc=not MODE_UJI), unsafe_allow_html=True)
                c2.button("Pilih", key=f"pilih_{i}", on_click=pilih_buku, args=(i,))
        if len(hasil) >= S["maks"]:
            st.button("Tampilkan lebih banyak", on_click=tambah_maks)

else:
    kiri = bar_atas()
    kiri.button("← Kembali", on_click=kembali)
    i = S["buku"]
    kotak_detail(i)
    if MODE_UJI:
        halaman_uji(i)
    else:
        halaman_demo(i)
