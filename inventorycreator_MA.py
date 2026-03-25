import requests
import random
import string

# -----------------------------------
# CONFIG
# -------------------------------
APP_HOST = "https://abbls2.sce.manh.com"
SEARCH_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/inventory/search"
SEARCH_LOCATION_URL = f"{APP_HOST}/dcinventory/api/dcinventory/location/search"
CREATE_INVENTORY_URL = f"{APP_HOST}/dcinventory/api/dcinventory/ilpn/createIlpnAndInventory"
ITEM_API_URL = f"{APP_HOST}/item-master/api/item-master/item/itemId"
ITEM_FACILITY_URL = f"{APP_HOST}/item-master/api/item-master/itemFacility/itemId"
DC_ORDER_URL = f"{APP_HOST}/dcorder/api/dcorder/originalOrder/save"
BATCH_MASTER_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster"
BATCH_SEARCH_URL = f"{APP_HOST}/dcinventory/api/dcinventory/batchMaster/search"
ITEM_DETAIL_URL = f"{APP_HOST}/item-master/api/item-master/item/itemId"  # for item details

LOC = "EDC-DEV"
ORG = "EDC-DEV"
HEADERS = {}

# -------------------------------
# UTIL
# -------------------------------
def set_headers(access_token):
    global HEADERS
    HEADERS = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "selectedLocation": LOC,
        "selectedOrganization": ORG
    }

def safe_json(response):
    try:
        return response.json()
    except:
        return {}

def generate_id(length=16):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# -------------------------------
# TOKEN VALIDATION
# -------------------------------
def validate_access_token(log):
    log("🔐 Validating ACCESS TOKEN...")
    payload = {"Query": "LocationId=EDC-DEV", "Size": 1}
    try:
        response = requests.post(SEARCH_LOCATION_URL, headers=HEADERS, json=payload)
    except Exception as e:
        log(f"❌ Connection error: {e}")
        return False
    data = safe_json(response)
    if response.status_code == 401:
        log("❌ Token expired")
        return False
    if data.get("errors") or data.get("exceptions"):
        log("❌ Token invalid")
        return False
    log("✅ ACCESS TOKEN VALID\n")
    return True

# -------------------------------
# GET LOCATION FROM ZONE
# -------------------------------
def get_location_from_zone(zone, log):
    payload = {
        "Query": f"PickAllocationZoneId={zone}",
        "Size": 50,
        "Templates": {"LocationId": ""}
    }
    try:
        response = requests.post(SEARCH_LOCATION_URL, headers=HEADERS, json=payload)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ Location API error: {e}")
        return None
    results = data.get("data", [])
    if not results:
        log(f"❌ No location found for zone: {zone}")
        return None
    location_id = results[0].get("LocationId")
    log(f"📍 Using Location: {location_id} (Zone: {zone})")
    return location_id

# -------------------------------
# GET ITEM DETAILS AND TrackBatchNumber
# -------------------------------
def get_item_and_batch_info(item_id, log):
    try:
        response = requests.get(f"{ITEM_DETAIL_URL}/{item_id}", headers=HEADERS)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ Item details API error: {e}")
        return {}
    return data.get("data", {})

# -------------------------------
# PACKZONE FROM ITEM
# -------------------------------
def get_packzone_from_item(item_id, log):
    log(f"\n📦 Fetching PackZone for Item: {item_id}")
    try:
        response = requests.get(f"{ITEM_FACILITY_URL}/{item_id}", headers=HEADERS)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ ItemFacility API error: {e}")
        return None
    data = data.get("data", {})
    packzone = None
    if data.get("Extended"):
        packzone = data["Extended"].get("PackZone")
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
# ITEM VALIDATION
# -------------------------------
def validate_item_batch(line, log):
    item_id = line.get("ItemId")
    batch = line.get("BatchNumber")
    try:
        response = requests.get(f"{ITEM_API_URL}/{item_id}", headers=HEADERS)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ Item API error: {e}")
        return "STOP"
    data = data.get("data")
    if not data:
        log("❌ Invalid item")
        return "STOP"
    track_batch = data.get("TrackBatchNumber")
    if isinstance(track_batch, str):
        track_batch = track_batch.lower() == "true"
    if not track_batch and batch:
        log("❌ Batch provided but item not batch tracked")
        return "STOP"
    if track_batch and not batch:
        new_batch = f"BATCH{generate_id(6)}"
        log(f"⚠️ Auto batch: {new_batch}")
        line["BatchNumber"] = new_batch
    return track_batch  # Return the batch tracking status

# -------------------------------
# SEARCH INVENTORY
# -------------------------------
def search_inventory(line, location_id, log):
    item = line.get("ItemId")
    qty = float(line.get("OrderedQuantity", 0))
    attr1 = line.get("ItemAttribute1")
    batch = line.get("BatchNumber")
    query_parts = [f"ItemId={item}", f"LocationId={location_id}"]
    if attr1:
        query_parts.append(f"InventoryAttribute1={attr1}")
    if batch:
        query_parts.append(f"BatchNumber={batch}")
    query = " and ".join(query_parts)
    log(f"\n🔍 Query: {query}")
    payload = {"Query": query, "Size": 100}
    try:
        response = requests.post(SEARCH_INVENTORY_URL, headers=HEADERS, json=payload)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ Inventory API error: {e}")
        return None
    results = data.get("data", [])
    for inv in results:
        if float(inv.get("OnHand", 0)) >= qty:
            return inv
    return None

# -------------------------------
# CREATE INVENTORY
# -------------------------------
def create_inventory(line, location_id, log, item_is_batch_tracked):
    if not item_is_batch_tracked:
        log("⚠️ Item is NOT batch tracked. Creating inventory without batch number.")
    else:
        log("✅ Item is batch tracked.")
    lpn = generate_id()
    inventory_payload = {
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
            "InventoryAttribute1": line.get("ItemAttribute1")
        }]
    }
    # Include BatchNumber only if item is batch tracked
    if item_is_batch_tracked:
        inventory_payload["Inventory"][0]["BatchNumber"] = line.get("BatchNumber")
    try:
        response = requests.post(CREATE_INVENTORY_URL, headers=HEADERS, json=inventory_payload)
    except Exception as e:
        log(f"❌ Create Inventory error: {e}")
        return
    log("\n🆕 CREATED INVENTORY")
    log(f"ItemId : {line.get('ItemId')}")
    log(f"ILPN : {lpn}")
    log(f"Location : {location_id}")
    log(f"Qty : {line.get('OrderedQuantity')}")
    if item_is_batch_tracked:
        log(f"Batch : {line.get('BatchNumber')}")
    else:
        log("Batch: N/A (Item not batch tracked)")
    log(f"Status : {response.status_code}")

# -------------------------------
# CHECK IF BATCH EXISTS
# -------------------------------
def check_batch_exists(batch_number, log):
    query = {
        "Query": f"BatchNumberId={batch_number}"
    }
    try:
        response = requests.post(BATCH_SEARCH_URL, headers=HEADERS, json=query)
        data = safe_json(response)
    except Exception as e:
        log(f"❌ Batch search API error: {e}")
        return False
    results = data.get("data", [])
    return len(results) > 0

# -------------------------------
# CREATE BATCH MASTER
# -------------------------------
def create_batch_master(item_id, batch_number, log):
    # Example received date, customize as needed
    received_date = "2022-05-20"
    payload = {
        "BatchNumberId": batch_number,
        "ItemId": item_id,
        "ReceivedDate": received_date,
        "VendorBatch": "AutoGenerated",
        "Status": 1000,
        "Expired": False,
        "ManufacturerRecall": False,
        "CountryOfOrigin": "US"
    }
    try:
        response = requests.post(BATCH_MASTER_URL, headers=HEADERS, json=payload)
        if response.status_code in [200, 201]:
            log(f"✅ Batch {batch_number} created successfully for Item {item_id}")
        else:
            log(f"❌ Failed to create batch {batch_number} for Item {item_id}")
            log(f"Response: {response.text}")
    except Exception as e:
        log(f"❌ Batch creation error: {e}")

# -------------------------------
# POST DO
# -------------------------------
def post_do_to_system(do_json, log):
    log("\n🚀 Posting user-provided DO to system...")
    log(f"Payload: {do_json}")
    try:
        response = requests.post(f"{APP_HOST}/dcorder/api/dcorder/originalOrder/save", headers=HEADERS, json=do_json)
    except Exception as e:
        log(f"❌ DO Post error: {e}")
        return
    log(f"Response Status: {response.status_code}")
    log(f"Response Text: {response.text}")
    if response.status_code in [200, 201]:
        log("✅ DO CREATED SUCCESSFULLY")
    else:
        log("❌ DO CREATION FAILED")

# -------------------------------
# MAIN PIPELINE
# -------------------------------
def process_order(do_json, log, access_token, zone):
    set_headers(access_token)
    if not validate_access_token(log):
        log("⛔ Invalid token. Stopping.")
        return
    location_id = get_location_from_zone(zone, log)
    if not location_id:
        return
    for line in do_json.get("OriginalOrderLine", []):
        log(f"\n===== Processing {line.get('ItemId')} =====")
        get_packzone_from_item(line.get("ItemId"), log)
        if validate_item_batch(line, log) == "STOP":
            continue
        item_id = line.get("ItemId")
        # Get item details to check TrackBatchNumber
        item_info = get_item_and_batch_info(item_id, log)
        track_batch = item_info.get("TrackBatchNumber")
        if isinstance(track_batch, str):
            track_batch = track_batch.lower() == "true"
        # Check if batch exists in system
        batch_number = line.get("BatchNumber")
        if batch_number:
            exists = check_batch_exists(batch_number, log)
            if not exists and track_batch:
                create_batch_master(item_id, batch_number, log)
        else:
            # Generate a new batch number
            batch_number = f"BATCH{generate_id(6)}"
            line["BatchNumber"] = batch_number
            # Only create batch if item is batch tracked
            if isinstance(track_batch, bool) and track_batch:
                exists = check_batch_exists(batch_number, log)
                if not exists:
                    create_batch_master(item_id, batch_number, log)

        # Search inventory
        inventory = search_inventory(line, location_id, log)
        if inventory:
            log("\n✅ INVENTORY FOUND")
            log(f"LPN : {inventory.get('InventoryContainerId')}")
            log(f"Location : {inventory.get('LocationId')}")
            log(f"Qty : {inventory.get('OnHand')}")
            if isinstance(track_batch, bool) and track_batch:
                log(f"Batch : {inventory.get('BatchNumber')}")
            else:
                log("Batch: N/A (Item not batch tracked)")
        else:
            log("❌ Not found → Creating")
            create_inventory(line, location_id, log, track_batch)
        log("\n==============================")
    log("📦 FINAL STEP: Posting DO")
    log("==============================")
    post_do_to_system(do_json, log)