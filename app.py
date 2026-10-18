from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import aiohttp
import requests
import json
import threading
import like_pb2
import uid_generator_pb2
import visit_count_pb2
from google.protobuf.message import DecodeError
from collections import OrderedDict

app = Flask(__name__)

VALID_API_KEYS = {"ZEXXY"}
daily_limit = 200
used_count = 0
lock = threading.Lock()

# ═══════════════════════ OB55 FULL HEADERS ═══════════════════════
# Ye headers OB55 client se match karte hain (latest Free Fire)
def ob55_headers(token):
    return {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 7 Build/TQ3A.230805.001)",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB55",
        # ✅ OB55 ke naye/important headers
        "X-Request-ID": "0",
        "X-Time-Zone": "Asia/Kolkata",
        "X-Country-Code": "IN",
        "X-Client-Language": "en",
        "X-Device-ID": "00000000-0000-0000-0000-000000000000",
    }


# ═══════════════════════ TOKEN LOADER ═══════════════════════
def load_tokens(region):
    try:
        if region == "IND":
            path = "token_ind.json"
        elif region in {"BR", "US", "SAC", "NA"}:
            path = "token_br.json"
        else:
            path = "token_bd.json"
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"Token load err {region}: {e}")
        return None


# ═══════════════════════ ENCRYPTION ═══════════════════════
def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plaintext, AES.block_size)
        return binascii.hexlify(cipher.encrypt(padded)).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Encrypt err: {e}")
        return None


def create_like_proto(user_id, region):
    try:
        m = like_pb2.like()
        m.uid = int(user_id)
        m.region = region
        return m.SerializeToString()
    except Exception as e:
        app.logger.error(f"Like proto err: {e}")
        return None


def create_uid_proto(uid):
    try:
        m = uid_generator_pb2.uid_generator()
        m.saturn_ = int(uid)
        m.garena = 1
        return m.SerializeToString()
    except Exception:
        return None


def enc(uid):
    proto = create_uid_proto(uid)
    if not proto:
        return None
    return encrypt_message(proto)


# ═══════════════════════ ASYNC REQUEST ═══════════════════════
async def send_request(encrypted_uid, token, url, session):
    try:
        edata = bytes.fromhex(encrypted_uid)
        async with session.post(url, data=edata, headers=ob55_headers(token)) as resp:
            return await resp.text()
    except Exception:
        return None


async def send_many(uid, region, url, count=100):
    """OB55 optimized — session reuse se fast."""
    try:
        proto = create_like_proto(uid, region)
        if not proto:
            return None
        enc_uid = encrypt_message(proto)
        if not enc_uid:
            return None
        tokens = load_tokens(region)
        if not tokens:
            return None

        # ✅ Connection pool — session reuse = 3x faster
        connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            for i in range(count):
                token = tokens[i % len(tokens)]["token"]
                tasks.append(send_request(enc_uid, token, url, session))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
    except Exception as e:
        app.logger.error(f"send_many err: {e}")
        return None


# ═══════════════════════ SYNC PROFILE FETCH ═══════════════════════
def make_request(encrypt_data, region, token):
    try:
        if region == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif region in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

        edata = bytes.fromhex(encrypt_data)
        r = requests.post(url, data=edata, headers=ob55_headers(token), verify=False, timeout=15)
        decoded = visit_count_pb2.Info()
        decoded.ParseFromString(r.content)
        return decoded
    except DecodeError as e:
        app.logger.error(f"Decode err: {e}")
        return None
    except Exception as e:
        app.logger.error(f"req err: {e}")
        return None


# ═══════════════════════ ROUTES ═══════════════════════
@app.route('/like', methods=['GET'])
def handle_requests():
    global used_count

    api_key = request.args.get("key")
    if api_key not in VALID_API_KEYS:
        return app.response_class(
            response=json.dumps({"error": "Invalid API key", "status": 3}, separators=(',', ':')),
            status=401, mimetype='application/json'
        )

    uid = request.args.get("uid")
    region = request.args.get("region", "").upper()

    if not uid or not region:
        return {"error": "UID and region required"}, 400

    try:
        tokens = load_tokens(region)
        if not tokens:
            raise Exception("Failed to load tokens")

        token = tokens[0]['token']
        enc_uid = enc(uid)
        if not enc_uid:
            raise Exception("Encryption failed")

        # ─── Before likes ───
        before = make_request(enc_uid, region, token)
        if not before:
            raise Exception("Initial fetch failed")
        before_like = before.AccountInfo.Likes

        # ─── Like endpoint ───
        if region == "IND":
            like_url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif region in {"BR", "US", "SAC", "NA"}:
            like_url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            like_url = "https://clientbp.ggpolarbear.com/LikeProfile"

        # ✅ asyncio.run ke bajaye new event loop (Flask thread-safe)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_many(uid, region, like_url, count=100))
            loop.close()
        except Exception as e:
            app.logger.error(f"send_many loop err: {e}")

        # ─── After likes ───
        after = make_request(enc_uid, region, token)
        if not after:
            raise Exception("Final fetch failed")
        after_like = after.AccountInfo.Likes

        like_given = after_like - before_like
        status = 1 if like_given > 0 else 2

        with lock:
            if status == 1:
                used_count += 1
            current_used = used_count

        result = OrderedDict([
            ("LikesGivenByAPI", like_given),
            ("LikesafterCommand", after_like),
            ("LikesbeforeCommand", before_like),
            ("PlayerNickname", after.AccountInfo.PlayerNickname),
            ("Level", after.AccountInfo.Levels),
            ("Region", after.AccountInfo.PlayerRegion),
            ("UID", after.AccountInfo.UID),
            ("status", status),
            ("daily_limit", daily_limit),
            ("used", current_used),
            ("remaining", max(daily_limit - current_used, 0)),
            ("ob_version", "OB55")
        ])

        return app.response_class(
            response=json.dumps(result, separators=(',', ':')),
            status=200, mimetype='application/json'
        )

    except Exception as e:
        app.logger.error(f"Like error: {e}")
        return {"error": str(e), "ob_version": "OB55"}, 500


@app.route('/remain', methods=['GET'])
def remain_info():
    global used_count
    remaining = max(daily_limit - used_count, 0)
    return jsonify({
        "daily_limit": daily_limit,
        "remaining": remaining,
        "used": used_count,
        "reset_info": "4:00 AM IST",
        "ob_version": "OB55"
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "ob_version": "OB55"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)