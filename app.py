import streamlit as st
import fitz  # PyMuPDF
import os
from streamlit_file_browser import st_file_browser

st.title("📝 Hapus Hyperlink 'Link Disposisi' dari PDF")

# ------------------------------
# PILIH FOLDER OUTPUT
# ------------------------------
st.write("### 📂 Pilih Folder Output")
selected_folder = st_file_browser(path=".", show_files=False, key="folder_browser")

if selected_folder:
    OUTPUT_FOLDER = selected_folder
else:
    OUTPUT_FOLDER = "pdf_output"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Info jumlah file di folder output
output_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.lower().endswith(".pdf")]
st.info(f"📂 Folder output aktif: `{OUTPUT_FOLDER}` (isi: {len(output_files)} file PDF)")

# ------------------------------
# INISIALISASI STATE
# ------------------------------
if "results" not in st.session_state:
    st.session_state["results"] = []
if "uploaded" not in st.session_state:
    st.session_state["uploaded"] = None

# Tombol reset tampilan
if st.button("🧹 Bersihkan Tampilan & Upload"):
    st.session_state["results"] = []
    st.session_state["uploaded"] = None
    st.success("✅ Tampilan dan daftar upload direset. File di folder output tetap aman.")
    st.stop()

# ------------------------------
# FILE UPLOADER
# ------------------------------
uploaded_files = st.file_uploader(
    "Upload file PDF", 
    type="pdf", 
    accept_multiple_files=True, 
    key="uploaded"
)

# ------------------------------
# PROSES PDF
# ------------------------------
if uploaded_files and OUTPUT_FOLDER:
    target_text = "Link Disposisi".lower()

    total_files = 0
    success = 0
    not_found = 0

    for uploaded_file in uploaded_files:
        total_files += 1
        input_pdf = uploaded_file.read()

        doc = fitz.open(stream=input_pdf, filetype="pdf")
        deleted = False

        for page_num, page in enumerate(doc, start=1):
            if deleted:
                break

            words = page.get_text("words")
            annots = page.annots()
            if annots:
                for annot in annots:
                    if annot.type[0] == 1:  # link annotation
                        rect = annot.rect
                        teks_link = " ".join(
                            w[4] for w in words if fitz.Rect(w[:4]).intersects(rect)
                        )
                        if target_text == teks_link.lower().strip():
                            page.delete_annot(annot)
                            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                            deleted = True
                            break

        if deleted:
            success += 1
            output_path = os.path.join(OUTPUT_FOLDER, uploaded_file.name)
            doc.save(output_path)
            st.session_state["results"].append(
                f"✅ {uploaded_file.name} → berhasil diproses & disimpan ke `{OUTPUT_FOLDER}`"
            )
        else:
            not_found += 1
            st.session_state["results"].append(
                f"⚠️ {uploaded_file.name} → teks 'Link Disposisi' tidak ditemukan (dilewati)"
            )

        doc.close()

    # Tambahkan ringkasan ke hasil
    st.session_state["results"].append("### 📊 Ringkasan")
    st.session_state["results"].append(f"- Total PDF diproses : **{total_files}**")
    st.session_state["results"].append(f"- Berhasil dihapus   : **{success}**")
    st.session_state["results"].append(f"- Dilewati (tidak ada): **{not_found}**")

# ------------------------------
# TAMPILKAN HASIL
# ------------------------------
for line in st.session_state["results"]:
    st.markdown(line)
