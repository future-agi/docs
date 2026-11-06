"""Contract test against a running Future AGI collector (skipped unless FI_API_KEY, FI_SECRET_KEY and FI_BASE_URL are set).

Cloudflare's exporter cannot set resource attributes, so the first test is the reason the page ships a collector.
"""
import json
import os
import urllib.error
import urllib.request

import pytest

import gateway_fixture as gf

KEY, SECRET, BASE = os.environ.get("FI_API_KEY"), os.environ.get("FI_SECRET_KEY"), os.environ.get("FI_BASE_URL")
pytestmark = pytest.mark.skipif(not (KEY and SECRET and BASE), reason="needs a local Future AGI (FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL)")
URL = (BASE or "").rstrip("/") + "/v1/traces"
PROJECT = "th8103-rest-cloudflare-ai-gateway-contract"


def post(raw, ctype="application/json", headers=None, extra=None):
    h = {"Content-Type": ctype}
    h.update({"X-Api-Key": KEY, "X-Secret-Key": SECRET} if headers is None else headers)
    h.update(extra or {})
    req = urllib.request.Request(URL, data=raw, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def body(resource=None):
    return gf.build_request(gf.GatewayRequest(), resource)


def test_rejects_a_batch_without_project_name():
    assert post(json.dumps(body()).encode()) == 400


def test_accepts_the_same_batch_with_project_name_json():
    assert post(json.dumps(body({"project_name": PROJECT})).encode()) == 200


def test_accepts_the_same_batch_with_project_name_protobuf():
    assert post(gf.to_protobuf(body({"project_name": PROJECT})), "application/x-protobuf") == 200


def test_wrong_keys_are_401():
    assert post(json.dumps(body({"project_name": PROJECT})).encode(), headers={"X-Api-Key": "x", "X-Secret-Key": "y"}) == 401


def test_a_bearer_header_like_the_one_on_cloudflares_page_is_401():
    assert post(json.dumps(body({"project_name": PROJECT})).encode(), headers={"Authorization": f"Bearer {KEY}"}) == 401


def test_gzip_bodies_are_refused_before_v1_56_and_accepted_after():
    import gzip
    # Set FI_EXPECT_GZIP_STATUS=400 only when checking self-hosted before v1.56.0.
    expected = int(os.environ.get("FI_EXPECT_GZIP_STATUS", "200"))
    assert expected in (200, 400)
    assert post(gzip.compress(json.dumps(body({"project_name": PROJECT})).encode()), extra={"Content-Encoding": "gzip"}) == expected
