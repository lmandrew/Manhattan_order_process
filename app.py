import streamlit as st
import json
import re

from inventorycreator_MA import process_order

st.set_page_config(page_title="DO Processor", layout="wide")

st.title("📦 DO Processing Tool")

# -------------------------------
# JSON CLEANER
# -------------------------------
def load_do_json(raw_text):

    lines = raw_text.splitlines()
    cleaned_lines = []

    for line in lines:
        if line.strip().startswith("//"):
            continue
        if "//" in line:
            line = line.split("//")[0]
        if line.strip():
            cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)

    try:
        return json.loads(cleaned)
    except:
        return None

# -------------------------------
# INPUT
# -------------------------------
st.subheader("📥 Input")

raw_json = st.text_area("📦 Paste DO JSON", height=350)

do_preview = load_do_json(raw_json)

item_label = "Item"

if do_preview and do_preview.get("OriginalOrderLine"):
    item_label = do_preview["OriginalOrderLine"][0].get("ItemId", "Item")

zone = st.text_input(f"📍 Enter Pick Zone for Item: {item_label}")

# -------------------------------
# RUN
# -------------------------------
run_process = st.button("🚀 Run Process")

# -------------------------------
# LOG AREA
# -------------------------------
st.subheader("📋 Logs")

log_container = st.empty()
logs = []

def log(msg):
    logs.append(msg)
    log_container.markdown("```\n" + "\n".join(logs) + "\n```")

if run_process:

    logs.clear()

    do_json = load_do_json(raw_json)

    if not do_json:
        log("❌ Invalid JSON")
        st.stop()

    if not zone:
        log("❌ Enter Pick Zone")
        st.stop()

    st.subheader("🧹 Cleaned JSON")
    st.json(do_json)

    try:
        process_order(do_json, log, zone)
        log("\n✅ Done")
    except Exception as e:
        log(f"❌ Error: {str(e)}")
