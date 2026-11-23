import io
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

import lambda_function as lf


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Op")


def make_event(*keys):
    return {"Records": [{
        "eventTime": "2026-11-23T12:00:00.000Z",
        "s3": {"bucket": {"name": "b"},
               "object": {"key": k, "size": 10, "eTag": "abc"}},
    } for k in keys]}


REC = {"id": "1", "name": "a", "updatedAt": 5}


#parse_event

def test_parse_event_basic():
    r = lf.parse_event(make_event("incoming/a.json"))
    assert r == [{"bucket": "b", "key": "incoming/a.json", "version": "abc",
                  "size": 10, "time": "2026-11-23T12:00:00.000Z"}]


def test_parse_event_decodes_key():
    r = lf.parse_event(make_event("incoming/my+file%D1%82.json"))
    assert r[0]["key"] == "incoming/my fileт.json"


def test_parse_event_multiple_records():
    assert len(lf.parse_event(make_event("incoming/a.json", "incoming/b.json"))) == 2


def test_parse_event_prefers_version_id():
    ev = make_event("incoming/a.json")
    ev["Records"][0]["s3"]["object"]["versionId"] = "v1"
    assert lf.parse_event(ev)[0]["version"] == "v1"


#mark_processed

@patch.object(lf, "TABLE")
def test_mark_processed_first_time(table):
    table.put_item.return_value = None
    assert lf.mark_processed("k") is True


@patch.object(lf, "TABLE")
def test_mark_processed_duplicate(table):
    table.put_item.side_effect = client_error("ConditionalCheckFailedException")
    assert lf.mark_processed("k") is False


@patch.object(lf, "TABLE")
def test_mark_processed_other_error_raises(table):
    table.put_item.side_effect = client_error("ThrottlingException")
    with pytest.raises(ClientError):
        lf.mark_processed("k")


#upsert_record

@patch.object(lf, "TABLE")
def test_upsert_uses_condition_on_updated_at(table):
    assert lf.upsert_record(REC) is True
    kw = table.update_item.call_args.kwargs
    assert "updatedAt < :u" in kw["ConditionExpression"]
    assert kw["Key"] == {"PK": "REC#1"}


@patch.object(lf, "TABLE")
def test_upsert_rejected_when_condition_fails(table):
    table.update_item.side_effect = client_error("ConditionalCheckFailedException")
    assert lf.upsert_record(REC) is False


@patch.object(lf, "TABLE")
def test_upsert_other_error_raises(table):
    table.update_item.side_effect = client_error("ProvisionedThroughputExceededException")
    with pytest.raises(ClientError):
        lf.upsert_record(REC)


#process_records

@patch.object(lf, "TABLE")
def test_process_records_counts_and_atomic_counter(table):
    table.update_item.side_effect = [
        None, client_error("ConditionalCheckFailedException"), None, None]
    recs = [{"id": str(i), "name": "n", "updatedAt": 1} for i in (1, 2, 3)]
    assert lf.process_records(recs) == (2, 1)
    last = table.update_item.call_args_list[-1].kwargs
    assert last["Key"] == {"PK": "STAT#rejected"}
    assert "ADD" in last["UpdateExpression"]
    assert last["ExpressionAttributeValues"][":n"] == 1


@patch.object(lf, "TABLE")
def test_no_counter_update_when_nothing_rejected(table):
    table.update_item.return_value = None
    assert lf.process_records([REC]) == (1, 0)
    assert table.update_item.call_count == 1


#handle_file

BODY = b'[{"id":"1","name":"a","updatedAt":1}]'
EV = {"bucket": "b", "key": "incoming/a.json", "version": "abc"}


@patch.object(lf, "TABLE")
@patch.object(lf, "S3")
def test_handle_file_duplicate_skips_processing(s3, table):
    s3.get_object.return_value = {"Body": io.BytesIO(BODY)}
    table.put_item.side_effect = client_error("ConditionalCheckFailedException")
    lf.handle_file(EV)
    table.update_item.assert_not_called()


@patch.object(lf, "TABLE")
@patch.object(lf, "S3")
def test_force_fail_raises_before_idempotency_marker(s3, table, monkeypatch):
    monkeypatch.setenv("FORCE_FAIL", "true")
    s3.get_object.return_value = {"Body": io.BytesIO(BODY)}
    with pytest.raises(RuntimeError):
        lf.handle_file(EV)
    table.put_item.assert_not_called()