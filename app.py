import streamlit as st
import json
import re

from inventorycreator_MA import process_order

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(page_title="DO Processor", layout="wide")

st.title("📦 DO Processing Tool")

# -------------------------------
# SESSION STATE
# -------------------------------
if "access_token" not in st.session_state:
    st.session_state.access_token = ""

# -------------------------------
# JSON CLEANER
# -------------------------------
def load_do_json(raw_text):

    lines = raw_text.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("//"):
            continue

        if "//" in line:
            line = line.split("//")[0]

        if line.strip():
            cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    try:
        return json.loads(cleaned)
    except:
        return None


# -------------------------------
# INPUT SECTION
# -------------------------------
st.subheader("📥 Input Section")

default_json = """{
    "OriginalOrderId": "TEST_001",
    "OriginalOrderLine": [
        {
            "ItemId": "06L4542",
            "OrderedQuantity": "1",
            "ItemAttribute1": "1530"
        }
    ]
}"""

raw_json = st.text_area("📦 Paste DO JSON", value=default_json, height=350)

# -------------------------------
# EXTRACT ITEM FOR DYNAMIC LABEL
# -------------------------------
do_json_preview = load_do_json(raw_json)

item_label = "Item"

if do_json_preview and do_json_preview.get("OriginalOrderLine"):
    first_item = do_json_preview["OriginalOrderLine"][0].get("ItemId")
    if first_item:
        item_label = first_item

# -------------------------------
# ACCESS TOKEN (SESSION BASED)
# -------------------------------
if not st.session_state.access_token:
    access_token_input = st.text_input("🔐 Enter Access Token", type="password")

    if access_token_input:
        st.session_state.access_token = access_token_input
        st.success("✅ Token saved for session")
else:
    st.success("🔐 Using saved access token")

# Reset token button
if st.button("🔄 Reset Token"):
    st.session_state.access_token = ""
    st.warning("Token cleared. Enter again.")

# -------------------------------
# DYNAMIC PACK ZONE INPUT
# -------------------------------
zone = st.text_input(
    f"📍 Enter Pick Zone for Item: {item_label}",
    value=""
)

# -------------------------------
# LOG AREA
# -------------------------------
st.subheader("📋 Execution Logs")

log_container = st.empty()
logs = []

def log(msg):
    logs.append(msg)
    log_container.markdown("```\n" + "\n".join(logs) + "\n```")


# -------------------------------
# RUN PIPELINE
# -------------------------------
def run_pipeline(do_json, zone):
    process_order(do_json, log, st.session_state.access_token, zone)


# -------------------------------
# BUTTON
# -------------------------------
if st.button("🚀 Run Process"):

    logs.clear()
    log("▶️ Starting process...\n")

    # -------------------------------
    # VALIDATIONS
    # -------------------------------
    if not st.session_state.access_token:
        log("❌ Please enter Access Token")
        st.stop()

    if not zone:
        log("❌ Please enter Pick Zone")
        st.stop()

    do_json = load_do_json(raw_json)

    if not do_json:
        log("❌ Invalid JSON (after cleaning)")
        st.stop()

    # -------------------------------
    # PREVIEW CLEANED JSON
    # -------------------------------
    st.subheader("🧹 Cleaned JSON Preview")
    st.json(do_json)

    # -------------------------------
    # RUN BACKEND
    # -------------------------------
    try:
        run_pipeline(do_json, zone)
        log("\n🏁 Process Completed Successfully")
    except Exception as e:
        log(f"\n❌ Error: {str(e)}")