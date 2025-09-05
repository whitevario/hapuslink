import streamlit as st
import io
import fitz  # PyMuPDF
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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

# Ganti dengan folder ID "TEMPAT HAPUS LINK DISPOSISI"
PARENT_FOLDER_ID = "1H87XOKnCFfBPW70-YUwSCF5SdPldhzHd"
REDIRECT_URI = "https://hapuslink.streamlit.app/"

st.set_page_config(page_title="Hapus Link Disposisi v6 Debug", page_icon="🐞")
st.title("🐞 Debug Hapus Link Disposisi (Shared Drive Fix)")

# -----------------------------
# Parse daftar nama folder
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
# Helper: list isi folder
# -----------------------------
def list_children(service, parent_id, title="Isi Folder"):
    children = service.files().list(
        q=f"'{parent_id}' in parents and trashed=false",
        corpora="allDrives",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = children.get("files", [])
    st.write(f"📂 {title}:")
    for f in files:
        st.write(f"- {f['name']} ({f['mimeType']})")
    return files

# -----------------------------
# Helper: cari folder fuzzy
# -----------------------------
def find_folder(service, parent_id, keyword, title="Cari Folder"):
    if not parent_id:
        return None
    list_children(service, parent_id, f"Isi dari {title}")
    query = (
        f"'{parent_id}' in parents and "
        f"name contains '{keyword}' and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(
        q=query,
        corpora="allDrives",
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

query_params = st.experimental_get_query_params()
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
# Step 2: Debug cek folder
# -----------------------------
bulan = st.selectbox("Pilih Bulan", bulan_list)
periode = st.radio("Pilih Periode", periode_list)

uploaded_files = st.file_uploader(
    "Upload file PDF (dummy untuk debug)",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files and st.button("🚀 Proses & Debug"):
    creds = Credentials.from_authorized_user_info(st.session_state.credentials)
    service = build("drive", "v3", credentials=creds)

    for file in uploaded_files:
        st.write(f"### 🔎 Debug {file.name}")

        perwakilan = list(folder_map.keys())[0]
        sekolah_full = folder_map[perwakilan][0]
        sekolah_clean = sekolah_full.split(". ", 1)[-1]

        perwakilan_obj = find_folder(service, PARENT_FOLDER_ID, perwakilan, "Root Drive")
        sekolah_obj = find_folder(service, perwakilan_obj["id"], sekolah_full, perwakilan) if perwakilan_obj else None
        pencairan_name = f"PENCAIRAN KASIR (DISPOSISI, BKK, KWITANSI) {sekolah_clean}"
        pencairan_obj = find_folder(service, sekolah_obj["id"], pencairan_name, sekolah_full) if sekolah_obj else None
        bulan_obj = find_folder(service, pencairan_obj["id"], bulan, pencairan_name) if pencairan_obj else None
        periode_obj = find_folder(service, bulan_obj["id"], periode, bulan) if bulan_obj else None

        if not all([perwakilan_obj, sekolah_obj, pencairan_obj, bulan_obj, periode_obj]):
            st.error("❌ Masih ada folder yang tidak ditemukan")
        else:
            st.success("✅ Semua folder ketemu!")
