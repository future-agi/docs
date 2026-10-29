# DeepSeek Harness (TH-8265)

Tracing for DeepSeek Harness is **not supported yet**; see `DECISION.md` and the docs page `src/pages/docs/integrations/deepseek-harness.mdx`.

| File | Purpose |
| --- | --- |
| `check_pin.sh` | Fetches three pinned `dsh` commits and proves they contain no trace SDK or trace exporter (with positive controls). Exit 0 = the page is still accurate, 1 = reopen the ticket, 2 = search not trusted. |
| `run_e2e.sh` | Reproduces the local spike with the third-party `@loongsuite/dsh-plugin`. Not a customer setup. |
| `tests/` | `test_check_pin.sh` (tiny git trees), `test_page_claims.py` (page vs recorded spike). |

```bash
bash check_pin.sh                       # needs network
bash tests/test_check_pin.sh            # offline
python3 -I tests/test_page_claims.py    # offline
# spike: needs a local Future AGI and an OpenAI-compatible endpoint, see the header of run_e2e.sh
CAPTURE=off bash run_e2e.sh
```
