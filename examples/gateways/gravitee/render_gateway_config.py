#!/usr/bin/env python3
"""Merge the shipped `services.opentelemetry` block into a Gateway gravitee.yml.

  render_gateway_config.py --base gravitee.yml --snippet rendered-snippet.yml --out out.yml

`--base` is the gravitee.yml shipped inside the graviteeio/apim-gateway image
(run_e2e.sh copies it out of the image). Everything else in it is kept; only
`services.opentelemetry` is replaced. This is the same edit a customer makes by hand.
"""
import argparse

import yaml

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--snippet", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--extra-attr", action="append", default=[], metavar="KEY=VALUE",
                help="add an extraAttributes entry (run_e2e.sh uses it to show that project_name cannot be set this way)")
ap.add_argument("--no-redaction", action="store_true",
                help="drop redactionRules (only used to inventory what Gravitee exports unmasked)")
a = ap.parse_args()
base = yaml.safe_load(open(a.base)) or {}
snippet = yaml.safe_load(open(a.snippet))
base.setdefault("services", {})
otel = snippet["services"]["opentelemetry"]
if a.extra_attr:
    otel["extraAttributes"] = [dict([kv.split("=", 1)]) for kv in a.extra_attr]
if a.no_redaction:
    otel.pop("redactionRules", None)
base["services"]["opentelemetry"] = otel
with open(a.out, "w") as f:
    yaml.safe_dump(base, f, sort_keys=False)
