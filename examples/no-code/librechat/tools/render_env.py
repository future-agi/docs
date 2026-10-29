#!/usr/bin/env python3
"""Render the files the test stack needs into RUN_DIR (never into this directory).

  render_env.py RUN_DIR

Writes (mode 600):
  RUN_DIR/librechat.env   LibreChat settings for the test (fresh random secrets) followed by the
                          Future AGI block from env/futureagi.env.example, with the two key placeholders
                          replaced by FI_API_KEY / FI_SECRET_KEY from the environment
  RUN_DIR/librechat.yaml  librechat.yaml with ${TEST_LLM_MODEL} filled in

Reads FI_API_KEY, FI_SECRET_KEY, TEST_LLM_BASE_URL, TEST_LLM_API_KEY, TEST_LLM_MODEL. Prints nothing secret.
"""
import os
import pathlib
import secrets
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
PLACEHOLDERS = {"YOUR_FUTURE_AGI_API_KEY": "FI_API_KEY", "YOUR_FUTURE_AGI_SECRET_KEY": "FI_SECRET_KEY"}


def librechat_base(env):
    """LibreChat settings that only the throwaway test stack needs."""
    return [
        "HOST=0.0.0.0",
        "PORT=3080",
        "MONGO_URI=mongodb://mongodb:27017/LibreChat",
        f"CREDS_KEY={secrets.token_hex(32)}",
        f"CREDS_IV={secrets.token_hex(16)}",
        f"JWT_SECRET={secrets.token_hex(32)}",
        f"JWT_REFRESH_SECRET={secrets.token_hex(32)}",
        "ALLOW_REGISTRATION=true",
        "ALLOW_EMAIL_LOGIN=true",
        "ALLOW_UNVERIFIED_EMAIL_LOGIN=true",
        "SEARCH=false",
        "NO_INDEX=true",
        "LIMIT_MESSAGE_IP=false",
        "LIMIT_CONCURRENT_MESSAGES=false",
        "BAN_VIOLATIONS=false",
        "LOGIN_MAX=100",  # the test logs in once per turn
        "REGISTER_MAX=20",
        "CONFIG_PATH=/app/librechat.yaml",
        "ENDPOINTS=agents,custom",
        f"TEST_LLM_BASE_URL={env['TEST_LLM_BASE_URL']}",
        f"TEST_LLM_API_KEY={env['TEST_LLM_API_KEY']}",
    ]


def render_block(text, env):
    """The page's env block with the key placeholders filled in. Fails if a placeholder is left."""
    for placeholder, var in PLACEHOLDERS.items():
        text = text.replace(placeholder, env[var])
    if "YOUR_" in text:
        raise SystemExit("unfilled placeholder in env/futureagi.env.example")
    return text


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    run_dir = pathlib.Path(argv[1])
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ
    missing = [v for v in ("FI_API_KEY", "FI_SECRET_KEY", "TEST_LLM_BASE_URL", "TEST_LLM_API_KEY",
                           "TEST_LLM_MODEL") if not env.get(v)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    block = render_block((HERE / "env" / "futureagi.env.example").read_text(), env)
    old = os.umask(0o077)
    try:
        (run_dir / "librechat.env").write_text("\n".join(librechat_base(env)) + "\n" + block)
        yaml_text = (HERE / "librechat.yaml").read_text().replace("${TEST_LLM_MODEL}", env["TEST_LLM_MODEL"])
        (run_dir / "librechat.yaml").write_text(yaml_text)
    finally:
        os.umask(old)
    (run_dir / "librechat.yaml").chmod(0o644)  # the container reads it as another user
    print(f"rendered librechat.env and librechat.yaml into {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
