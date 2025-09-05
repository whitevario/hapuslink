import streamlit as st
import io
import fitz  # PyMuPDF
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# -----------------------------
# Konfigurasi Google OAuth
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

client_config = {
    "web": {
        "client_id": st.secrets["google_oauth"]["client_id"],
        "project_id": st.secrets["google_oauth"]["project_id"],
        "auth_uri": st.secrets["google_oauth"]["auth_uri"],
        "token_uri": st.secrets["google_oauth"]["token_uri"],
        "client_secret": st.secrets["google_oauth"]["client_secret"],
        "redirect_uris": st.secrets["google_oauth"]["redirect_uris"],
    }
}

# Root Shared Drive
PARENT_FOLDER_ID = "1H87XOKnCFfBPW70-YUwSCF5SdPldhzHd"
REDIRECT_URI = "https://hapuslink.streamlit.app/"

st.set_page_config(page_title="Hapus Link Disposisi v4", page_icon="📝")
st.title("📝 Hapus Hyperlink 'Link Disposisi' dan Upload ke Shared Drive")

# -----------------------------
# Helper: baca file daftar nama folder
# -----------------------------
def parse_folder_file(file_path="daftar nama folder.txt"):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    data = {}
    bulan = []
    periode = []
    current_perwakilan = None
    mode = None

    for line in lines:
        if line.startswith("[PERWAKILAN]"):
            mode = "perwakilan"
            continue
        if line.startswith("[SEKOLAH]"):
            mode = "sekolah"
            continue
        if line.startswith("[BULAN]"):
            mode = "bulan"
            continue
        if line.startswith("[PERIODE]"):
            mode = "periode"
            continue

        if mode == "perwakilan":
            current_perwakilan = line
            data[current_perwakilan] = []
        elif mode == "sekolah" and current_perwakilan:
            data[current_perwakilan].append(line)
        elif mode == "bulan":
            bulan.append(line)
        elif mode == "periode":
            periode.append(line)

    return data, bulan, periode

folder_map, bulan_list, periode_list = parse_folder_file("daftar nama folder.txt")

# -----------------------------
# Helper: cari folder exact
# -----------------------------
def find_folder(service, parent_id, name):
    query = (
        f"'{parent_id}' in parents and "
        f"name='{name}' and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name, webViewLink)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    items = results.get("files", [])
    return items[0] if items else None

# -----------------------------
# Helper: cari folder fuzzy (pakai contains)
# -----------------------------
def find_folder_contains(service, parent_id, keyword):
    query = (
        f"'{parent_id}' in parents and "
        f"name contains '{keyword}' and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name, webViewLink)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    items = results.get("files", [])
    return items[0] if items else None

# -----------------------------
# Step 1: Autentikasi
# -----------------------------
if "credentials" not in st.session_state:
    st.session_state.credentials = None

query_params = st.query_params()
if "code" in query_params and st.session_state.credentials is None:
    code = query_params["code"][0]
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    st.session_state.credentials = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "id_token": creds.id_token,
        "scopes": creds.scopes,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "token_uri": creds.token_uri,
    }
    st.rerun()

if st.session_state.credentials is None:
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    st.markdown(f"👉 [Klik di sini untuk login Google]({auth_url})")
    st.stop()
else:
    creds = Credentials.from_authorized_user_info(st.session_state.credentials)
    st.success("✅ Sudah login ke Google Drive")

# -----------------------------
# Step 2: Upload + Mapping Folder
# -----------------------------
bulan = st.selectbox("Pilih Bulan", bulan_list)
periode = st.radio("Pilih Periode", periode_list)

uploaded_files = st.file_uploader(
    "Upload file PDF",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    st.write("### Atur Perwakilan & Sekolah untuk tiap file:")

    if "file_choices" not in st.session_state:
        st.session_state.file_choices = {}

    for file in uploaded_files:
        if file.name not in st.session_state.file_choices:
            first_perwakilan = list(folder_map.keys())[0]
            st.session_state.file_choices[file.name] = {
                "perwakilan": first_perwakilan,
                "sekolah": folder_map[first_perwakilan][0]
            }

        pilihan = st.session_state.file_choices[file.name]

        col1, col2 = st.columns(2)
        with col1:
            pilihan["perwakilan"] = st.selectbox(
                f"Perwakilan untuk {file.name}",
                list(folder_map.keys()),
                index=list(folder_map.keys()).index(pilihan["perwakilan"]),
                key=f"perwakilan_{file.name}"
            )
        with col2:
            pilihan["sekolah"] = st.selectbox(
                f"Sekolah untuk {file.name}",
                folder_map[pilihan["perwakilan"]],
                index=folder_map[pilihan["perwakilan"]].index(pilihan["sekolah"]) if pilihan["sekolah"] in folder_map[pilihan["perwakilan"]] else 0,
                key=f"sekolah_{file.name}"
            )

    if st.button("🚀 Proses & Upload Semua"):
        creds = Credentials.from_authorized_user_info(st.session_state.credentials)
        service = build("drive", "v3", credentials=creds)

        uploaded_folders = set()
        for file in uploaded_files:
            pilihan = st.session_state.file_choices[file.name]
            perwakilan = pilihan["perwakilan"]
            sekolah_full = pilihan["sekolah"]
            sekolah_clean = sekolah_full.split(". ", 1)[-1]  # buang nomor

            # cek folder bertingkat
            perwakilan_obj = find_folder(service, PARENT_FOLDER_ID, perwakilan)
            sekolah_obj = find_folder(service, perwakilan_obj["id"], sekolah_full) if perwakilan_obj else None
            pencairan_name = f"PENCAIRAN KASIR (DISPOSISI, BKK, KWITANSI) {sekolah_clean}"
            pencairan_obj = find_folder(service, sekolah_obj["id"], pencairan_name) if sekolah_obj else None
            bulan_obj = find_folder(service, pencairan_obj["id"], bulan) if pencairan_obj else None
            periode_obj = find_folder_contains(service, bulan_obj["id"], periode) if bulan_obj else None

            if not all([perwakilan_obj, sekolah_obj, pencairan_obj, bulan_obj, periode_obj]):
                st.error(f"❌ Folder tidak lengkap untuk {file.name} → {perwakilan}/{sekolah_full}/{pencairan_name}/{bulan}/{periode}")
                continue

            # hapus link disposisi
            input_pdf = file.read()
            doc = fitz.open(stream=input_pdf, filetype="pdf")
            for page in doc:
                rects = page.search_for("Link Disposisi", quads=False)
                for rect in rects:
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()
                    annots = page.annots()
                    if annots:
                        for annot in annots:
                            if rect.intersects(annot.rect):
                                page.delete_annot(annot)

            output_buffer = io.BytesIO()
            doc.save(output_buffer)
            doc.close()
            output_buffer.seek(0)

            # upload ke Drive
            file_metadata = {"name": file.name, "parents": [periode_obj["id"]]}
            media = MediaIoBaseUpload(output_buffer, mimetype="application/pdf")
            service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()

            st.success(f"✅ {file.name} → berhasil diupload ke {perwakilan}/{sekolah_full}/{pencairan_name}/{bulan}/{periode_obj['name']}")
            uploaded_folders.add(periode_obj["webViewLink"])

        st.markdown("### 📂 Folder Tujuan")
        for link in uploaded_folders:
            st.markdown(f"- 🔗 [Buka Folder Tujuan]({link})")

# -----------------------------
# Reset Upload
# -----------------------------
if st.button("🔄 Reset Upload"):
    if "file_choices" in st.session_state:
        del st.session_state["file_choices"]
    st.rerun()

