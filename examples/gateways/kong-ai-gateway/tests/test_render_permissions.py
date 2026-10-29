"""Linux bind mounts must be readable by Kong without exposing host keys."""
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[1]


def test_render_keeps_host_directory_private_and_allows_container_group(tmp_path):
    evidence = tmp_path / "evidence"
    config = evidence / "kong.yml"
    env = dict(os.environ, EVID=str(evidence), UPSTREAM_API_KEY="test-provider",
               UPSTREAM_MODEL="gpt-4o-mini", UPSTREAM_CHAT_URL="https://api.openai.com/v1/chat/completions",
               LOG_PAYLOADS="false", FI_TRACES_ENDPOINT="http://capture:4318/tracer/v1/traces",
               FI_API_KEY="test-api", FI_SECRET_KEY="test-secret", FI_PROJECT_NAME="test-project")
    subprocess.run(["bash", "-c", 'source "$1"; render "$2"', "test", str(HERE / "lib.sh"), str(config)],
                   env=env, check=True)
    assert evidence.stat().st_mode & 0o777 == 0o700
    assert config.stat().st_mode & 0o777 == 0o640
    assert "test-provider" in config.read_text()


def test_start_passes_rendered_config_group_to_container(tmp_path):
    config = tmp_path / "kong.yml"
    config.write_text("test")
    output = tmp_path / "docker-args.txt"
    env = dict(os.environ, EVID=str(tmp_path / "evidence"), ARGS=str(output))
    script = r'''source "$1"
      docker() { printf '%s\n' "$*" >> "$ARGS"; }
      wait_kong_ready() { return 0; }
      start_kong "$2"
    '''
    subprocess.run(["bash", "-c", script, "test", str(HERE / "lib.sh"), str(config)], env=env, check=True)
    assert "--group-add " + str(config.stat().st_gid) in output.read_text()
