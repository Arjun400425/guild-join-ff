from flask import Flask, request, jsonify, Response
import requests
import jwt
import urllib3
import json
from collections import OrderedDict
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import ReqCLan_pb2
import QuitClanReq_pb2
import my_pb2
import output_pb2

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)

OB = "OB55"

API_INFO = {
    "developer": "ZEXXY",
    "telegram": "@ZEXXY_H4X",
    "api_name": "FF GUILD JOIN/LEAVE API",
    "version": OB
}

# Crypto keys (same as original)
KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

# Headers used for game requests
GAME_HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/octet-stream",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA": "v1 1",
    "ReleaseVersion": OB,
    "Expect": "100-continue"
}

LOGIN_HEADERS = GAME_HEADERS.copy()

# Region → Server URL mapping
REGION_SERVER_MAP = {
    "IND": "https://client.ind.freefiremobile.com",   # India
    "ME":  "https://clientbp.ggpolarbear.com",        # Middle East
    "VN":  "https://clientbp.ggpolarbear.com",        # Vietnam
    "BD":  "https://clientbp.ggpolarbear.com",        # Bangladesh
    "PK":  "https://clientbp.ggpolarbear.com",        # Pakistan
    "SG":  "https://clientbp.ggpolarbear.com",        # Singapore
    "BR":  "https://client.us.freefiremobile.com",    # Brazil
    "NA":  "https://client.us.freefiremobile.com",    # North America
    "ID":  "https://clientbp.ggpolarbear.com",        # Indonesia
    "RU":  "https://clientbp.ggpolarbear.com",        # Russia
    "TH":  "https://clientbp.ggpolarbear.com",        # Thailand
}
DEFAULT_SERVER_URL = "https://clientbp.ggpolarbear.com"   # fallback
LOGIN_URL = "https://loginbp.ggpolarbear.com"             # same for all regions

# Helper: encrypt payload with AES-CBC
def encrypt_payload(data):
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    return cipher.encrypt(pad(data, AES.block_size))

# Helper: decode JWT without verifying signature
def decode_jwt(token):
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        account_id = str(decoded.get("account_id"))
        nickname = decoded.get("nickname")
        lock_region = decoded.get("lock_region")
        return account_id, nickname, lock_region
    except Exception as e:
        print(f"JWT Decode error: {e}")
        return None, None, None

# Helper: get server URL based on region (with fallback)
def get_server_url(region):
    return REGION_SERVER_MAP.get(region, DEFAULT_SERVER_URL)

# NEW: Get JWT directly from UID and Password using external API
def get_jwt_from_uid_password(uid, password):
    url = f"http://zexxy-jwt-gen.vercel.app/token?uid={uid}&password={password}"
    try:
        print(f"Calling JWT API: {url}")
        r = requests.get(url, timeout=10)
        data = r.json()
        print(f"JWT API Response: {data}")
        
        # Check if token exists in response (without requiring success key)
        if "token" in data:
            jwt_token = data["token"]
            account_id, nickname, region = decode_jwt(jwt_token)
            if account_id:
                print(f"Successfully got JWT for UID: {account_id}, Region: {region}")
                return jwt_token, account_id, nickname, region
            else:
                print("Failed to decode JWT - invalid token format")
                return None, None, None, None
        else:
            # Try to get error message
            error_msg = data.get("error", "No token in response")
            print(f"JWT API error: {error_msg}")
            return None, None, None, None
    except Exception as e:
        print(f"get_jwt_from_uid_password error: {e}")
        return None, None, None, None

# Perform major login (used when using UID/pass) - DEPRECATED but kept for compatibility
def perform_major_login(access_token, open_id):
    try:
        game = my_pb2.GameData()
        game.timestamp = "2024-12-05 18:15:32"
        game.game_name = "free fire"
        game.game_version = 1
        game.version_code = "1.123.2"
        game.os_info = "Android OS 12 / API-31"
        game.device_type = "Handheld"
        game.network_provider = "Verizon"
        game.connection_type = "WIFI"
        game.screen_width = 1080
        game.screen_height = 2340
        game.dpi = "420"
        game.cpu_info = "ARM64"
        game.total_ram = 5951
        game.gpu_name = "Adreno"
        game.gpu_version = "OpenGL ES 3.0"
        game.user_id = "Google|dummy"
        game.ip_address = "172.190.111.97"
        game.language = "en"
        game.open_id = open_id
        game.access_token = access_token
        game.platform_type = 4   # single platform
        game.field_99 = "4"
        game.field_100 = "4"
        encrypted = encrypt_payload(game.SerializeToString())
        r = requests.post(LOGIN_URL, headers=LOGIN_HEADERS, data=encrypted, verify=False, timeout=10)
        print("MajorLogin status:", r.status_code)
        if r.status_code == 200 and len(r.content) > 5:
            msg = output_pb2.Garena_420()
            msg.ParseFromString(r.content)
            if msg.token:
                print("JWT generated successfully")
                return msg.token
    except Exception as e:
        print("Login attempt failed:", e)
    return None

# Guest login (UID/pass) -> access_token + open_id - DEPRECATED but kept for compatibility
def guest_login(uid, password):
    payload = {
        "uid": uid,
        "password": password,
        "response_type": "token",
        "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }
    headers = {"User-Agent": "GarenaMSDK/4.0.19P9"}
    try:
        r = requests.post("https://100067.connect.garena.com/oauth/guest/token/grant",
                          data=payload, headers=headers, verify=False, timeout=10)
        data = r.json()
        return data.get("access_token"), data.get("open_id")
    except Exception as e:
        print("Guest login error:", e)
        return None, None

# Convert access_token to JWT using external API
def get_jwt_from_access_token(access_token):
    url = f"https://acesstojwt-sigma.vercel.app/token?access_token={access_token}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("success") and "token" in data:
            jwt_token = data["token"]
            account_id, nickname, region = decode_jwt(jwt_token)
            return jwt_token, account_id, nickname, region
        else:
            print("External API error:", data)
            return None, None, None, None
    except Exception as e:
        print("get_jwt_from_access_token error:", e)
        return None, None, None, None

# Join clan request
def request_clan(jwt_token, clan_id, region):
    server_url = get_server_url(region)
    msg = ReqCLan_pb2.MyMessage()
    msg.field_1 = int(clan_id)
    payload = encrypt_payload(msg.SerializeToString())
    headers = GAME_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}"
    url = f"{server_url}/RequestJoinClan"
    print(f"Sending join request to: {url}")
    r = requests.post(url, headers=headers, data=payload, verify=False)
    print(f"Join clan response status: {r.status_code}")
    print(f"Join clan response text: {r.text[:200]}")  # Print first 200 chars
    return r.status_code, r.text

# Quit clan request
def quit_clan(jwt_token, clan_id, region):
    server_url = get_server_url(region)
    msg = QuitClanReq_pb2.QuitClanReq()
    msg.field_1 = int(clan_id)
    payload = encrypt_payload(msg.SerializeToString())
    headers = GAME_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}"
    url = f"{server_url}/QuitClan"
    r = requests.post(url, headers=headers, data=payload, verify=False)
    return r.status_code, r.text

# Resolve login method and return (jwt, uid, name, region, method)
def resolve_login(jwt_token=None, uid=None, password=None, access_token=None):
    # 1. Direct JWT
    if jwt_token:
        uid, name, region = decode_jwt(jwt_token)
        if uid:
            return jwt_token, uid, name, region, "JWT"
        else:
            return None, None, None, None, "Invalid JWT"

    # 2. Access token (new)
    if access_token:
        jwt_token, uid, name, region = get_jwt_from_access_token(access_token)
        if jwt_token:
            return jwt_token, uid, name, region, "ACCESS_TOKEN"
        else:
            return None, None, None, None, "Access token conversion failed"

    # 3. UID + password (UPDATED - using JWT generation API)
    if uid and password:
        # Use the direct JWT generation API
        jwt_token, uid, name, region = get_jwt_from_uid_password(uid, password)
        if jwt_token:
            return jwt_token, uid, name, region, "UID_PASS"
        else:
            return None, None, None, None, "UID/Password authentication failed - Invalid credentials or API error"

    return None, None, None, None, "No login credentials provided"

# ---------------------------
# Endpoints
# ---------------------------

@app.route("/")
def home():
    data = OrderedDict()
    data["success"] = True
    data["message"] = "Free Fire Clan API"
    data["examples"] = {
        "request_clan_jwt": "/request_clan?clan_id=123&jwt=JWT",
        "request_clan_uidpass": "/request_clan?clan_id=123&uid=123&pass=PASS",
        "request_clan_accesstoken": "/request_clan_access?clan_id=123&access_token=TOKEN",
        "quit_clan_jwt": "/quit_clan?clan_id=123&jwt=JWT",
        "quit_clan_uidpass": "/quit_clan?clan_id=123&uid=123&pass=PASS",
        "quit_clan_accesstoken": "/quit_clan_access?clan_id=123&access_token=TOKEN"
    }
    return Response(json.dumps(data, indent=2), mimetype="application/json")

# Original endpoints (jwt or uid+pass)
@app.route("/request_clan")
def api_request():
    clan_id = request.args.get("clan_id")
    jwt_token = request.args.get("jwt")
    uid = request.args.get("uid")
    password = request.args.get("pass") or request.args.get("password")  # Support both 'pass' and 'password'
    
    if not clan_id:
        return jsonify({"success": False, "error": "clan_id required"})

    print(f"Request: clan_id={clan_id}, uid={uid}, has_password={bool(password)}")
    
    final_jwt, uid, name, region, method = resolve_login(jwt_token=jwt_token, uid=uid, password=password)
    if not final_jwt:
        return jsonify({"success": False, "error": method})

    print(f"Login successful: UID={uid}, Name={name}, Region={region}, Method={method}")
    
    code, text = request_clan(final_jwt, clan_id, region)
    success = (code == 200)
    
    response_data = {
        "success": success,
        "action": "Join Clan",
        "clan_id": clan_id,
        "uid": uid,
        "name": name,
        "region": region,
        "login_method": method,
        "developer": API_INFO["developer"],
        "telegram": API_INFO["telegram"],
        "api_version": API_INFO["version"],
        "http_status_code": code,
        "server_response": text[:500] if text else "Empty response"  # Limit response length
    }
    
    if not success:
        response_data["error_details"] = "Request failed - check server response for details"
    
    return jsonify(response_data)

@app.route("/quit_clan")
def api_quit():
    clan_id = request.args.get("clan_id")
    jwt_token = request.args.get("jwt")
    uid = request.args.get("uid")
    password = request.args.get("pass") or request.args.get("password")
    
    if not clan_id:
        return jsonify({"success": False, "error": "clan_id required"})

    final_jwt, uid, name, region, method = resolve_login(jwt_token=jwt_token, uid=uid, password=password)
    if not final_jwt:
        return jsonify({"success": False, "error": method})

    code, text = quit_clan(final_jwt, clan_id, region)
    success = (code == 200)
    return jsonify({
        "success": success,
        "action": "Quit Clan",
        "clan_id": clan_id,
        "uid": uid,
        "name": name,
        "region": region,
        "login_method": method,
        "developer": API_INFO["developer"],
        "telegram": API_INFO["telegram"],
        "api_version": API_INFO["version"],
        "server_response": text
    })

# New endpoints using access_token
@app.route("/request_clan_access")
def api_request_access():
    clan_id = request.args.get("clan_id")
    access_token = request.args.get("access_token")
    if not clan_id:
        return jsonify({"success": False, "error": "clan_id required"})
    if not access_token:
        return jsonify({"success": False, "error": "access_token required"})

    final_jwt, uid, name, region, method = resolve_login(access_token=access_token)
    if not final_jwt:
        return jsonify({"success": False, "error": method})

    code, text = request_clan(final_jwt, clan_id, region)
    success = (code == 200)
    return jsonify({
        "success": success,
        "action": "Join Clan",
        "clan_id": clan_id,
        "uid": uid,
        "name": name,
        "region": region,
        "login_method": method,
        "developer": API_INFO["developer"],
        "telegram": API_INFO["telegram"],
        "api_version": API_INFO["version"],
        "server_response": text
    })

@app.route("/quit_clan_access")
def api_quit_access():
    clan_id = request.args.get("clan_id")
    access_token = request.args.get("access_token")
    if not clan_id:
        return jsonify({"success": False, "error": "clan_id required"})
    if not access_token:
        return jsonify({"success": False, "error": "access_token required"})

    final_jwt, uid, name, region, method = resolve_login(access_token=access_token)
    if not final_jwt:
        return jsonify({"success": False, "error": method})

    code, text = quit_clan(final_jwt, clan_id, region)
    success = (code == 200)
    return jsonify({
        "success": success,
        "action": "Quit Clan",
        "clan_id": clan_id,
        "uid": uid,
        "name": name,
        "region": region,
        "login_method": method,
        "developer": API_INFO["developer"],
        "telegram": API_INFO["telegram"],
        "api_version": API_INFO["version"],
        "server_response": text
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    