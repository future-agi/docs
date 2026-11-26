#!/usr/bin/env python3
"""STAND-IN for the TypeSafe System One API. This is NOT TypeSafe and NOT Jev.

A small local server shaped like TypeSafe's published OpenAPI document
(https://api.typesafe.ai/openapi.json, version 0.2.0, read 2026-10-16) so the
real ``typesafe-sdk`` client can run end to end without a TypeSafe key:

* ``POST /v1/systemone``: ``{model, state, questions[, assets]}`` in,
  ``{model, answers, usage}`` out. ``noul`` answers carry only ``noul``;
  ``choice`` answers ``choice``, ``confidence`` and ``probabilities``;
  ``score`` answers ``score``, ``confidence``, ``legend`` and
  ``probabilities``; ``box`` answers ``box`` and ``confidence: null``.
* ``GET /v1/models``: ``{"models": [{name, description, release_date}]}``.
* Errors use the bodies api.typesafe.ai returned on 2026-10-16: 403 with no
  key, 401 for a key starting ``ts-invalid``, and FastAPI-style 422
  ``{"detail": [{loc, msg, type}]}`` for a body that breaks the schema.
* Every response has an ``x-typesafe-request-id`` header.

Answers are deterministic numbers derived from a hash of the request. They
are not model output and say nothing about how Jev decides. ``jev-latest``
resolves to ``jev-1.13.0`` in the response, as the API documents for aliases.

Usage: ``python systemone_stub.py --port 8765``. Binds 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

MODELS = [
    {"name": "jev-latest", "description": "General-purpose system one model.", "release_date": "2026-09-15"},
    {"name": "jev-1.13.0", "description": "General-purpose system one model.", "release_date": "2026-09-15"},
]
ALIASES = {"jev-latest": "jev-1.13.0"}
QUESTION_TYPES = ("noul", "choice", "score", "box")
NO_KEY = {"detail": {"error_type": "authentication_error", "message": "Must supply an API key! Check your request and try again."}}
BAD_KEY = {"detail": {"error_type": "authentication_error", "message": "Cannot authenticate with the server. Please check your API key and try again."}}


def _unit(*parts: str) -> float:
    """A deterministic number in (0, 1) from the request."""
    digest = hashlib.sha256("\x1f".join(parts).encode()).digest()
    return (int.from_bytes(digest[:4], "big") % 9973 + 1) / 9975


def _distribution(names: List[str], seed: str) -> Dict[str, float]:
    weights = [_unit(seed, name) ** 2 for name in names]
    total = sum(weights)
    return {name: round(weight / total, 4) for name, weight in zip(names, weights)}


def _answer(name: str, question: Dict[str, Any], state_key: str) -> Dict[str, Any]:
    kind = question["type"]
    seed = "{0}|{1}|{2}".format(state_key, name, json.dumps(question, sort_keys=True))
    if kind == "noul":
        return {"type": "noul", "noul": round(_unit(seed), 4)}
    if kind == "choice":
        probabilities = _distribution(list(question["criteria"]), seed)
        choice = max(probabilities, key=probabilities.get)
        return {"type": "choice", "choice": choice, "confidence": probabilities[choice], "probabilities": probabilities}
    if kind == "score":
        levels = [str(index) for index in range(len(question["criteria"]))]
        probabilities = _distribution(levels, seed)
        score = round(sum(int(level) * p for level, p in probabilities.items()), 4)
        return {
            "type": "score",
            "score": score,
            "confidence": max(probabilities.values()),
            "legend": dict(zip(levels, question["criteria"])),
            "probabilities": probabilities,
        }
    top, left = round(_unit(seed, "t") / 2, 4), round(_unit(seed, "l") / 2, 4)
    return {"type": "box", "box": {"top": top, "bottom": round(top + 0.25, 4), "left": left, "right": round(left + 0.25, 4)}, "confidence": None}


def validate(body: Any) -> List[Dict[str, Any]]:
    """FastAPI-style validation errors for the SystemOneRequest schema (empty when valid)."""
    if not isinstance(body, dict):
        return [{"loc": ["body"], "msg": "Input should be a valid dictionary", "type": "dict_type"}]
    errors: List[Dict[str, Any]] = []
    for field in ("model", "state", "questions"):
        if field not in body:
            errors.append({"loc": ["body", field], "msg": "Field required", "type": "missing"})
    if "model" in body and not isinstance(body["model"], str):
        errors.append({"loc": ["body", "model"], "msg": "Input should be a valid string", "type": "string_type"})
    if "state" in body and not isinstance(body["state"], (str, dict, list)):
        errors.append({"loc": ["body", "state"], "msg": "Input should be a valid string", "type": "string_type"})
    questions = body.get("questions")
    if "questions" in body:
        if not isinstance(questions, dict):
            errors.append({"loc": ["body", "questions"], "msg": "Input should be a valid dictionary", "type": "dict_type"})
        elif not questions:
            errors.append({"loc": ["body", "questions"], "msg": "Dictionary should have at least 1 item after validation, not 0", "type": "too_short"})
        else:
            for name, question in questions.items():
                kind = question.get("type") if isinstance(question, dict) else None
                if kind not in QUESTION_TYPES:
                    errors.append({"loc": ["body", "questions", name], "msg": "Input tag does not match any of the expected tags", "type": "union_tag_invalid"})
                elif kind == "choice" and "criteria" not in question:
                    errors.append({"loc": ["body", "questions", name, "choice", "criteria"], "msg": "Field required", "type": "missing"})
                elif kind == "choice" and not isinstance(question["criteria"], dict):
                    errors.append({"loc": ["body", "questions", name, "choice", "criteria"], "msg": "Input should be a valid dictionary", "type": "dict_type"})
                elif kind == "score" and not (isinstance(question.get("criteria"), list) and question["criteria"]):
                    errors.append({"loc": ["body", "questions", name, "score", "criteria"], "msg": "List should have at least 1 item after validation, not 0", "type": "too_short"})
    return errors


def _decode_body(content: bytes, encoding: str, content_type: str) -> Any:
    if encoding == "zstd":
        try:
            from compression.zstd import decompress  # Python 3.14
        except ImportError:
            from backports.zstd import decompress  # typesafe-sdk[zstd] on Python < 3.14
        content = decompress(content)
    if content_type.startswith("multipart/form-data"):
        boundary = content_type.split("boundary=", 1)[1].strip('"').encode()
        for part in content.split(b"--" + boundary):
            head, _, data = part.partition(b"\r\n\r\n")
            if b'name="request"' in head:
                return json.loads(data.rstrip(b"\r\n"))
        raise ValueError("no request part")
    return json.loads(content)


class Handler(BaseHTTPRequestHandler):
    server_version = "systemone-standin/1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet: never log bodies or keys
        return

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.send_header("x-typesafe-request-id", "req_standin_" + uuid.uuid4().hex)
        self.end_headers()
        self.wfile.write(payload)

    def _auth(self) -> Optional[Tuple[int, Any]]:
        header = self.headers.get("authorization", "")
        if not header.lower().startswith("bearer ") or not header[7:].strip():
            return 403, NO_KEY
        if header[7:].strip().startswith("ts-invalid"):
            return 401, BAD_KEY
        return None

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            return self._send(200, {"ok": True, "standin": True})
        if self.path.split("?")[0] != "/v1/models":
            return self._send(404, {"detail": "Not Found"})
        failure = self._auth()
        if failure:
            return self._send(*failure)
        return self._send(200, {"models": MODELS})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/v1/systemone":
            return self._send(404, {"detail": "Not Found"})
        failure = self._auth()
        if failure:
            return self._send(*failure)
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length)
        try:
            body = _decode_body(raw, self.headers.get("content-encoding", ""), self.headers.get("content-type", ""))
        except Exception:
            return self._send(422, {"detail": [{"loc": ["body"], "msg": "JSON decode error", "type": "json_invalid"}]})
        errors = validate(body)
        if errors:
            return self._send(422, {"detail": errors})
        state_key = json.dumps(body["state"], sort_keys=True)
        answers = {name: _answer(name, question, state_key) for name, question in body["questions"].items()}
        self._send(
            200,
            {
                "model": ALIASES.get(body["model"], body["model"]),
                "answers": answers,
                "usage": {"input_tokens": max(1, len(raw) // 4), "output_tokens": 2 * len(answers)},
            },
        )


def serve(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = serve(args.port)
    print("STANDIN System One (not TypeSafe) on http://127.0.0.1:{0}".format(server.server_address[1]), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
