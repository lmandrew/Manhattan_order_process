import requests
import random
import string
import json
import time
import re

# -----------------------------------
# CONFIG
# --------------------------------------
APP_HOST = "https://abbls2.sce.manh.com"

SEARCH_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/inventory/search"
SEARCH_LOCATION_URL = f"{APP_HOST}/dcinventory/api/dcinventory/location/search"
CREATE_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/ilpn/createIlpnAndInventory"
ITEM_API_URL = f"{APP_HOST}/item-master/api/item-master/item/itemId"
DC_ORDER_URL = f"{APP_HOST}/dcorder/api/dcorder/originalOrder/save"
BATCH_MASTER_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster"
BATCH_SEARCH_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster/search"

TOKEN_URL = "https://abbls2-auth.sce.manh.com/auth/realms/maactive/protocol/openid-connect/token"

USERNAME = "andrew.l@abbott.com"
PASSWORD = "1526John@"
BASIC_AUTH = "Basic b21uaWNvbXBvbmVudC4xLjAuMDpiNHM4cmdUeWc1NVhZTnVu"

LOC = "EDC-DEV"
ORG = "EDC-DEV"

# -------------------------------
# TOKEN CACHE
# -------------------------------
token_cache = {"access_token": None, "created_time": 0}

def get_access_token():
    if token_cache["access_token"] and (time.time() - token_cache["created_time"] < 3000):
        return token_cache["access_token"]

    payload = {
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": BASIC_AUTH
    }

    response = requests.post(TOKEN_URL, data=payload, headers=headers)

    if response.status_code != 200:
        raise Exception(f"❌ Token fetch failed: {response.text}")

    token_cache["access_token"] = response.json().get("access_token")
    token_cache["created_time"] = time.time()

    print("✅ Token refreshed")

    return token_cache["access_token"]

def get_headers():
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "selectedLocation": LOC,
        "selectedOrganization": ORG
    }

def make_request(method, url, **kwargs):
    kwargs["headers"] = get_headers()
    response = requests.request(method, url, **kwargs)

    if response.status_code == 401:
        token_cache["access_token"] = None
        kwargs["headers"] = get_headers()
        response = requests.request(method, url, **kwargs)

    return response

# -------------------------------
# JSON CLEANER
# -------------------------------
def clean_json(raw_text):
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
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    return json.loads(cleaned)

# -------------------------------
# UTIL
# -------------------------------
def safe_json(response):
    try:
        return response.json()
    except:
        return {}

def generate_batch():
    return f"BATCH{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

def generate_lpn():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# -------------------------------
# LOCATION
# -------------------------------
def get_location_from_zone(zone, log):
    payload = {
        "Query": f"PickAllocationZoneId={zone}",
        "Size": 50,
        "Templates": {"LocationId": ""}
    }

    response = make_request("POST", SEARCH_LOCATION_URL, json=payload)
    data = safe_json(response)

    results = data.get("data", [])

    if not results:
        log(f"❌ No location found for zone: {zone}")
        return None

    loc = results[0].get("LocationId")
    log(f"📍 Using Location: {loc}")
    return loc

# -------------------------------
# CHECK BATCH EXISTS
# -------------------------------
def check_batch_exists(batch):
    payload = {"Query": f"BatchNumberId={batch}"}
    response = make_request("POST", BATCH_SEARCH_URL, json=payload)
    data = safe_json(response)
    return len(data.get("data", [])) > 0

# -------------------------------
# CREATE BATCH MASTER
# -------------------------------
def create_batch_master(item_id, batch, log):
    payload = {
        "BatchNumberId": batch,
        "ItemId": item_id,
        "ReceivedDate": "2022-01-01",
        "Status": 1000,
        "ExpirationDate": "2035-12-31",
        "CountryOfOrgin": "USA",
        "Expired": False,
        "ManufacturerRecall": False
    }

    response = make_request("POST", BATCH_MASTER_URL, json=payload)

    if response.status_code in [200, 201]:
        log(f"✅ Batch Master Created: {batch}")
    else:
        log(f"❌ Batch Master Failed: {response.text}")

# -------------------------------
# HANDLE BATCH LOGIC
# -------------------------------
def handle_batch_logic(line, log):

    item_id = line.get("ItemId")
    batch = line.get("BatchNumber")

    response = make_request("GET", f"{ITEM_API_URL}/{item_id}")
    data = safe_json(response).get("data")

    if not data:
        log("❌ Invalid item")
        return "STOP", False

    track_batch = data.get("TrackBatchNumber")

    if isinstance(track_batch, str):
        track_batch = track_batch.lower() == "true"

    log(f"📦 Item {item_id} → Batch Tracked: {'YES' if track_batch else 'NO'}")

    # -------------------------------
    # CASE 1: Batch tracked
    # -------------------------------
    if track_batch:
        if not batch:
            batch = generate_batch()
            line["BatchNumber"] = batch
            log(f"⚠️ Generated Batch: {batch}")

        # create batch master if not exists
        if not check_batch_exists(batch):
            create_batch_master(item_id, batch, log)

    # -------------------------------
    # CASE 2: NOT batch tracked
    # -------------------------------
    else:
        if batch:
            log("⚠️ Removing batch (not batch tracked)")
            line.pop("BatchNumber", None)

    return None, track_batch

# -------------------------------
# SEARCH INVENTORY
# -------------------------------
def search_inventory(line, location_id):
    item = line.get("ItemId")
    qty = float(line.get("OrderedQuantity", 0))

    query = f"ItemId={item} and LocationId={location_id}"

    response = make_request("POST", SEARCH_INVENTORY_URL, json={"Query": query, "Size": 100})
    data = safe_json(response)

    for inv in data.get("data", []):
        if float(inv.get("OnHand", 0)) >= qty:
            return inv

    return None

# -------------------------------
# CREATE INVENTORY
# -------------------------------
def create_inventory(line, location_id, track_batch, log):

    lpn = generate_lpn()

    payload = {
        "IlpnId": lpn,
        "IlpnTypeId": "ILPN",
        "Status": "3000",
        "CurrentLocationId": location_id,
        "Inventory": [{
            "InventoryContainerId": lpn,
            "ItemId": line.get("ItemId"),
            "OnHand": line.get("OrderedQuantity")
        }]
    }

    if track_batch:
        payload["Inventory"][0]["BatchNumber"] = line.get("BatchNumber")

    make_request("POST", CREATE_INVENTORY_URL, json=payload)

    log(f"🆕 Inventory Created → LPN: {lpn}")

# -------------------------------
# POST DO
# -------------------------------
def post_do(do_json, log):

    log("\n🚀 Posting FINAL DO JSON...")

    response = make_request("POST", DC_ORDER_URL, json=do_json)

    log(f"Status: {response.status_code}")

    try:
        log(json.dumps(response.json(), indent=2))
    except:
        log(response.text)

# -------------------------------
# MAIN PIPELINE
# -------------------------------
def process_order(input_data, log, zone):

    # -------------------------------
    # HANDLE BOTH STRING & DICT
    # -------------------------------
    if isinstance(input_data, str):
        do_json = clean_json(input_data)
    elif isinstance(input_data, dict):
        do_json = input_data
    else:
        log("❌ Invalid input type")
        return

    # -------------------------------
    # NORMAL FLOW
    # -------------------------------
    location_id = get_location_from_zone(zone, log)

    if not location_id:
        return

    for line in do_json.get("OriginalOrderLine", []):

        log(f"\n===== Processing {line.get('ItemId')} =====")

        stop, track_batch = handle_batch_logic(line, log)

        if stop == "STOP":
            continue

        inv = search_inventory(line, location_id)

        if inv:
            log("✅ Inventory exists")
        else:
            create_inventory(line, location_id, track_batch, log)

    log("\n📦 FINAL STEP")
    post_do(do_json, log)