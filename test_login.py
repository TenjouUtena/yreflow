"""Quick test: can we authenticate to Wolfery with username+password over WebSocket?

Usage:
    python test_login.py <username> <password>

Sends:
    1. version {"protocol": "1.2.3"}
    2. auth.auth.login {name, hash}  (HMAC-SHA256 with pepper)
    3. call.auth.getUser

Prints every message received so we can see what works.
"""

import sys
import json
import hmac
import hashlib
import base64
import asyncio

import websockets
from websockets.asyncio.client import connect


PEPPER = b"TheStoryStartsHere"
URI = "wss://api.wolfery.com/"


def compute_hash(password: str) -> str:
    """HMAC-SHA256 of password with public pepper, base64-encoded."""
    h = hmac.new(PEPPER, password.strip().encode("utf-8"), hashlib.sha256)
    return base64.b64encode(h.digest()).decode("ascii")


async def test_login(username: str, password: str) -> None:
    msg_id = 0

    def next_id():
        nonlocal msg_id
        msg_id += 1
        return msg_id

    print(f"Connecting to {URI} (no auth cookie)...")

    async with connect(URI) as ws:
        print("Connected!\n")

        # Step 1: version
        vid = next_id()
        msg = {"id": vid, "method": "version", "params": {"protocol": "1.2.3"}}
        print(f">>> {json.dumps(msg)}")
        await ws.send(json.dumps(msg))

        resp = await ws.recv()
        print(f"<<< {resp}\n")

        # Step 2: auth.auth.login
        login_hash = compute_hash(password)
        lid = next_id()
        msg = {
            "id": lid,
            "method": "auth.auth.login",
            "params": {"name": username, "hash": login_hash},
        }
        print(f">>> {json.dumps(msg)}")
        await ws.send(json.dumps(msg))

        resp = await ws.recv()
        j = json.loads(resp)
        print(f"<<< {resp}\n")

        if "error" in j:
            print(f"AUTH FAILED: {j['error']}")
            return

        print("Auth response received. Sending call.auth.getUser...")

        # Step 3: getUser
        uid = next_id()
        msg = {"id": uid, "method": "call.auth.getUser"}
        print(f">>> {json.dumps(msg)}")
        await ws.send(json.dumps(msg))

        resp = await ws.recv()
        j = json.loads(resp)
        print(f"<<< {json.dumps(j, indent=2)[:2000]}\n")

        if "error" in j:
            print(f"getUser FAILED: {j['error']}")
            return

        if "result" in j and "rid" in j["result"]:
            print(f"SUCCESS! Player RID: {j['result']['rid']}")
        else:
            print(f"Unexpected response format.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_login.py <username> <password>")
        sys.exit(1)

    asyncio.run(test_login(sys.argv[1], sys.argv[2]))
