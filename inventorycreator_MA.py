import requests
import random
import string
import json
import time

# -----------------------------------
# CONFIG
# --------------------------------------
APP_HOST = "https://abbls2.sce.manh.com"

SEARCH_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/inventory/search"
SEARCH_LOCATION_URL = f"{APP_HOST}/dcinventory/api/dcinventory/location/search"
CREATE_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/ilpn/createIlpnAndInventory"
ITEM_API_URL = f"{APP_HOST}/item-master/api/item-master/item/itemId"
ITEM_FACILITY_URL = f"{APP_HOST}/item-master/api/item-master/itemFacility/itemId"
DC_ORDER_URL = f"{APP_HOST}/dcorder/api/dcorder/originalOrder/save"
BATCH_MASTER_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster"
BATCH_SEARCH_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster/search"

# -------------------------------
# AUTH CONFIG
# -------------------------------
TOKEN_URL = "https://abbls2-auth.sce.manh.com/auth/realms/maactive/protocol/openid-connect/token"

USERNAME = "andrew.l@abbott.com"
PASSWORD = "1526John@"

BASIC_AUTH = "Basic b21uaWNvbXBvbmVudC4xLjAuMDpiNHM4cmdUeWc1NVhZTnVu"

LOC = "EDC-DEV"
ORG = "EDC-DEV"

# -------------------------------
# TOKEN CACHE
# -------------------------------
token_cache = {
    "access_token": None,
    "created_time": 0
}

# -------------------------------
# GET ACCESS TOKEN (AUTO)
# -------------------------------
def get_access_token():

    # reuse token for ~50 minutes
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

    data = response.json()

    token_cache["access_token"] = data.get("access_token")
    token_cache["created_time"] = time.time()

    print("✅ New Access Token Generated")

    return token_cache["access_token"]

# -------------------------------
# HEADERS BUILDER
# -------------------------------
def get_headers():
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "selectedLocation": LOC,
        "selectedOrganization": ORG
    }

# -------------------------------
# SAFE REQUEST (AUTO RETRY)
# -------------------------------
def make_request(method, url, **kwargs):

    headers = get_headers()
    kwargs["headers"] = headers

    response = requests.request(method, url, **kwargs)

    # auto retry if token expired
    if response.status_code == 401:
        print("🔄 Token expired → refreshing...")

        token_cache["access_token"] = None  # force refresh

        headers = get_headers()
        kwargs["headers"] = headers

        response = requests.request(method, url, **kwargs)

    return response

# -------------------------------
# UTIL
# -------------------------------
def safe_json(response):
    try:
        return response.json()
    except:
        return {}

def generate_id(length=16):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# -------------------------------
# LOCATION FROM ZONE
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

    location_id = results[0].get("LocationId")

    log(f"📍 Using Location: {location_id} (Zone: {zone})")

    return location_id

# -------------------------------
# ITEM INFO
# -------------------------------
def get_item_info(item_id):
    response = make_request("GET", f"{ITEM_API_URL}/{item_id}")
    return safe_json(response).get("data", {})

# -------------------------------
# PACKZONE
# -------------------------------
def get_packzone_from_item(item_id, log):

    log(f"\n📦 Fetching PackZone for Item: {item_id}")

    response = make_request("GET", f"{ITEM_FACILITY_URL}/{item_id}")
    data = safe_json(response).get("data", {})

    packzone = data.get("Extended", {}).get("PackZone")

    if not packzone:
        packzone = (
            data.get("EntityLabels", {})
            .get("AttributeLabels", {})
            .get("Extended", {})
            .get("PackZone")
        )

    log(f"✅ PackZone: {packzone}" if packzone else "⚠️ PackZone not found")

    return packzone

# -------------------------------
# VALIDATION
# -------------------------------
def validate_item_batch(line, log):

    item_id = line.get("ItemId")
    batch = line.get("BatchNumber")

    data = get_item_info(item_id)

    if not data:
        log("❌ Invalid item")
        return "STOP", False

    track_batch = data.get("TrackBatchNumber")

    if isinstance(track_batch, str):
        track_batch = track_batch.lower() == "true"

    if not track_batch and batch:
        log("❌ Batch provided but item not batch tracked")
        return "STOP", False

    if track_batch and not batch:
        batch = f"BATCH{generate_id(6)}"
        line["BatchNumber"] = batch
        log(f"⚠️ Auto batch created: {batch}")

    return None, track_batch

# -------------------------------
# SEARCH INVENTORY
# -------------------------------
def search_inventory(line, location_id, log):

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
def create_inventory(line, location_id, log, track_batch):

    lpn = generate_id()

    payload = {
        "IlpnId": lpn,
        "IlpnTypeId": "ILPN",
        "Status": "3000",
        "CurrentLocationTypeId": "Storage",
        "CurrentLocationId": location_id,
        "Inventory": [{
            "InventoryContainerId": lpn,
            "InventoryContainerTypeId": "ILPN",
            "ItemId": line.get("ItemId"),
            "OnHand": line.get("OrderedQuantity"),
        }]
    }

    if track_batch:
        payload["Inventory"][0]["BatchNumber"] = line.get("BatchNumber")

    response = make_request("POST", CREATE_INVENTORY_URL, json=payload)

    log("\n🆕 CREATED INVENTORY")
    log(f"ItemId : {line.get('ItemId')}")
    log(f"ILPN   : {lpn}")
    log(f"Loc    : {location_id}")
    log(f"Qty    : {line.get('OrderedQuantity')}")
    log(f"Status : {response.status_code}")

# -------------------------------
# POST DO
# -------------------------------
def post_do(do_json, log):

    log("\n🚀 Posting DO...")

    response = make_request("POST", DC_ORDER_URL, json=do_json)

    log(f"Status: {response.status_code}")

    try:
        log(json.dumps(response.json(), indent=2))
    except:
        log(response.text)

# -------------------------------
# MAIN PIPELINE
# -------------------------------
def process_order(do_json, log, zone):

    location_id = get_location_from_zone(zone, log)

    if not location_id:
        return

    for line in do_json.get("OriginalOrderLine", []):

        log(f"\n===== {line.get('ItemId')} =====")

        get_packzone_from_item(line.get("ItemId"), log)

        stop, track_batch = validate_item_batch(line, log)

        if stop == "STOP":
            continue

        inv = search_inventory(line, location_id, log)

        if inv:
            log("\n✅ INVENTORY FOUND")
            log(f"LPN : {inv.get('InventoryContainerId')}")
            log(f"Loc : {inv.get('LocationId')}")
        else:
            create_inventory(line, location_id, log, track_batch)

    log("\n📦 FINAL STEP")
    post_do(do_json, log)