"""The APIM stand-in does what policy/otlp-egress.policy.xml says, and nothing more."""
import urllib.error
import urllib.request

from conftest import GW_FI_KEY, GW_FI_SECRET, SUB_KEY

BODY = b"\x0a\x00 not-really-otlp"


def post(url, path="/tracer/v1/traces", headers=None, body=BODY):
    req = urllib.request.Request(url + path, data=body, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_forwards_body_unchanged_and_sets_the_two_future_agi_headers(apim, backend):
    assert post(apim.url, headers={"Ocp-Apim-Subscription-Key": SUB_KEY, "Content-Type": "application/x-protobuf"}) == 200
    (r,) = backend.requests
    assert r["body"] == BODY
    assert r["path"] == "/tracer/v1/traces"
    assert r["headers"]["x-api-key"] == GW_FI_KEY and r["headers"]["x-secret-key"] == GW_FI_SECRET
    assert r["headers"]["content-type"] == "application/x-protobuf"


def test_the_callers_credentials_never_reach_future_agi(apim, backend):
    post(apim.url, headers={"Ocp-Apim-Subscription-Key": SUB_KEY, "Authorization": "Bearer caller-secret",
                            "X-Api-Key": "caller-supplied", "X-Secret-Key": "caller-supplied"})
    (r,) = backend.requests
    assert "ocp-apim-subscription-key" not in r["headers"] and "authorization" not in r["headers"]
    assert r["headers"]["x-api-key"] == GW_FI_KEY  # the policy overrides what the caller sent
    assert SUB_KEY.encode() not in r["body"] and b"caller-secret" not in str(r["headers"]).encode()


def test_subscription_key_is_required_and_nothing_is_forwarded_without_it(apim, backend):
    assert post(apim.url) == 401
    assert post(apim.url, headers={"Ocp-Apim-Subscription-Key": "wrong"}) == 401
    assert backend.requests == []
    assert post(apim.url, path=f"/tracer/v1/traces?subscription-key={SUB_KEY}") == 200  # APIM also accepts the query form


def test_only_the_one_operation_exists(apim, backend):
    h = {"Ocp-Apim-Subscription-Key": SUB_KEY}
    assert post(apim.url, path="/v1/traces", headers=h) == 404
    assert post(apim.url, path="/tracer/v1/logs", headers=h) == 404
    assert backend.requests == []


def test_backend_status_is_passed_through(apim, backend):
    backend.status = 401
    assert post(apim.url, headers={"Ocp-Apim-Subscription-Key": SUB_KEY}) == 401
    backend.status = 400
    assert post(apim.url, headers={"Ocp-Apim-Subscription-Key": SUB_KEY}) == 400
