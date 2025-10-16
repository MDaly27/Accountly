# lambda_function.py — DynamoDB creds API with safe two-step upsert
# Table: accountly-credentials  (region us-east-2)
# PK: "act-name" (String)
#
# Item shape:
# {
#   "act-name": "<username>",
#   "creds": {
#       "<service>": { "username": "...", "password": "...", "updated_at": <epoch> }
#   },
#   "created_at": <epoch>,
#   "updated_at": <epoch>
# }
from decimal import Decimal
import json
import time
import base64
import boto3
from botocore.exceptions import ClientError

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)

def _resp(code: int, body: dict):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }

REGION = "us-east-2"
TABLE_NAME = "accountly-credentials"
PK_ATTR = "act-name"

DDB = boto3.resource("dynamodb", region_name=REGION)
TABLE = DDB.Table(TABLE_NAME)

def _get_method(event):
    m = (event.get("requestContext", {}).get("http", {}) or {}).get("method")
    return m or event.get("httpMethod", "GET")

def _get_path(event):
    p = (event.get("requestContext", {}).get("http", {}) or {}).get("path")
    return p or event.get("path", "/")

def _get_query(event):
    return event.get("queryStringParameters") or {}

def _get_path_params(event):
    return event.get("pathParameters") or {}

def _get_body(event):
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body)
    except Exception:
        return {}

def lambda_handler(event, context):
    method = _get_method(event)
    path = _get_path(event)
    query = _get_query(event)
    path_params = _get_path_params(event)
    payload = _get_body(event)

    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    # ---------- POST /creds (upsert one service) ----------
    if method == "POST" and path.endswith("/creds"):
        username  = payload.get("username")
        service   = (payload.get("service") or "").strip()
        cred_user = payload.get("cred_username") or payload.get("username")
        password  = payload.get("password")

        if not username or not service or password is None:
            return _resp(400, {"error": "required: username (non-empty), service (non-empty), password"})

        now = int(time.time())

        try:
            # Step 1: ensure 'creds' exists as a Map (no overlap with child paths)
            TABLE.update_item(
                Key={PK_ATTR: username},
                UpdateExpression="SET #creds = if_not_exists(#creds, :empty), "
                                 "updated_at = :now, "
                                 "created_at = if_not_exists(created_at, :now)",
                ExpressionAttributeNames={"#creds": "creds"},
                ExpressionAttributeValues={":empty": {}, ":now": now},
                ReturnValues="NONE"
            )

            # Step 2: set the specific service entry
            TABLE.update_item(
                Key={PK_ATTR: username},
                UpdateExpression="SET #creds.#svc = :val, updated_at = :now",
                ExpressionAttributeNames={"#creds": "creds", "#svc": service},
                ExpressionAttributeValues={
                    ":val": {"username": (cred_user or username), "password": password, "updated_at": now},
                    ":now": now
                },
                ReturnValues="NONE"
            )

        except ClientError as e:
            return _resp(500, {"error": "ddb_update_failed", "detail": str(e)})
        except Exception as e:
            return _resp(500, {"error": "unexpected", "detail": str(e)})

        return _resp(200, {"ok": True, "username": username, "service": service})

    # ---------- GET /creds?username=... (list services; hide passwords) ----------
    if method == "GET" and path.endswith("/creds") and not path_params.get("service"):
        username = query.get("username")
        if not username:
            return _resp(400, {"error": "username query param required"})
        try:
            res = TABLE.get_item(Key={PK_ATTR: username})
            item = res.get("Item") or {}
            creds = item.get("creds") or {}
            listing = {svc: {"username": data.get("username")} for svc, data in creds.items()}
            return _resp(200, {"username": username, "services": listing})
        except ClientError as e:
            return _resp(500, {"error": "ddb_get_failed", "detail": str(e)})

    # ---------- GET /creds/{service}?username=... (fetch one; includes password) ----------
    if method == "GET" and path_params.get("service"):
        username = query.get("username")
        service = path_params["service"]
        if not username:
            return _resp(400, {"error": "username query param required"})
        try:
            res = TABLE.get_item(Key={PK_ATTR: username})
            item = res.get("Item") or {}
            data = (item.get("creds") or {}).get(service)
            if not data:
                return _resp(404, {"error": "not found"})
            return _resp(200, {"username": username, "service": service, **data})
        except ClientError as e:
            return _resp(500, {"error": "ddb_get_failed", "detail": str(e)})

    return _resp(404, {"error": "route not found"})

