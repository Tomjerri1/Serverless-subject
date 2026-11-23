import json
import os
import time
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
S3 = boto3.client("s3")
TTL_SEC = 3 * 24 * 3600


def log(level, msg, **kw):
    print(json.dumps({"level": level, "msg": msg, **kw}, ensure_ascii=False))


def parse_event(event):
    result = []
    for r in event["Records"]:
        obj = r["s3"]["object"]
        result.append({
            "bucket": r["s3"]["bucket"]["name"],
            "key": unquote_plus(obj["key"]),
            "version": obj.get("versionId") or obj.get("eTag", ""),
            "size": obj.get("size", 0),
            "time": r["eventTime"],
        })
    return result


def mark_processed(idem_key):
    now = int(time.time())
    try:
        TABLE.put_item(
            Item={"PK": f"IDEMP#{idem_key}", "processedAt": now, "ttl": now + TTL_SEC},
            ConditionExpression="attribute_not_exists(PK)")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return False


def upsert_record(rec):
    try:
        TABLE.update_item(
            Key={"PK": f"REC#{rec['id']}"},
            UpdateExpression="SET #n = :n, updatedAt = :u",
            ConditionExpression="attribute_not_exists(PK) OR updatedAt < :u",
            ExpressionAttributeNames={"#n": "name"},
            ExpressionAttributeValues={":n": rec["name"], ":u": rec["updatedAt"]})
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return False


def count_rejected(n):
    TABLE.update_item(
        Key={"PK": "STAT#rejected"},
        UpdateExpression="ADD #r :n SET updatedAt = :now",
        ExpressionAttributeNames={"#r": "rejected"},
        ExpressionAttributeValues={":n": n, ":now": int(time.time())})


def process_records(records):
    accepted = rejected = 0
    for rec in records:
        if upsert_record(rec):
            accepted += 1
        else:
            rejected += 1
    if rejected:
        count_rejected(rejected)
    return accepted, rejected


def handle_file(ev):
    body = S3.get_object(Bucket=ev["bucket"], Key=ev["key"])["Body"].read()
    records = json.loads(body)
    if os.environ.get("FORCE_FAIL") == "true":
        raise RuntimeError("forced failure")
    idem_key = f"{ev['bucket']}/{ev['key']}#{ev['version']}"
    if not mark_processed(idem_key):
        log("INFO", "duplicate, skipped", key=idem_key)
        return
    accepted, rejected = process_records(records)
    log("INFO", "file processed", key=ev["key"], accepted=accepted, rejected=rejected)


def lambda_handler(event, context):
    log("INFO", "event", event=event)
    for ev in parse_event(event):
        handle_file(ev)