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

def get_order_lines(do_json):
    if not do_json:
        return []
    return do_json.get("OriginalOrderLine") or []

# -------------------------------
# INPUT
# -------------------------------
st.subheader("📥 Input")

raw_json = st.text_area("📦 Paste DO JSON", height=350)

do_preview = load_do_json(raw_json)
order_lines = get_order_lines(do_preview)
line_zones = {}

if order_lines:
    st.subheader("📍 Pick Allocation Zones")
    for index, line in enumerate(order_lines, start=1):
        line_id = str(line.get("OriginalOrderLineId", index))
        item_id = line.get("ItemId", "Item")
        qty = line.get("OrderedQuantity", "N/A")
        label = f"Line {line_id} | Item {item_id} | Qty {qty}"
        line_zones[line_id] = st.text_input(
            label,
            key=f"pick_zone_{line_id}"
        )

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

    if not order_lines:
        log("❌ No order lines found in DO JSON")
        st.stop()

    missing_line_ids = []
    zone_map = {}

    for index, line in enumerate(order_lines, start=1):
        line_id = str(line.get("OriginalOrderLineId", index))
        zone_value = (line_zones.get(line_id) or "").strip()

        if not zone_value:
            missing_line_ids.append(line_id)
        else:
            zone_map[line_id] = zone_value

    if missing_line_ids:
        log(f"❌ Enter Pick Zone for Order Line(s): {', '.join(missing_line_ids)}")
        st.stop()

    st.subheader("🧹 Cleaned JSON")
    st.json(do_json)

    try:
        process_order(do_json, log, zone_map)
        log("\n✅ Done")
    except Exception as e:
        log(f"❌ Error: {str(e)}")
