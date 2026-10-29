"""The docs page shows the same configuration as the example that was tested: python -m pytest tools/tests"""
import re
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2]
PAGE = EXAMPLE.parents[2] / "src" / "pages" / "docs" / "integrations" / "frameworks" / "embabel.mdx"
JAVA = EXAMPLE / "src" / "main" / "java" / "ai" / "futureagi" / "examples" / "embabel"


def block(title: str) -> str:
    match = re.search(r'```\w+ title="%s"\n(.*?)```' % re.escape(title), PAGE.read_text(), re.S)
    assert match, f"no code block titled {title} on the page"
    return match.group(1)


def code_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.split("//")[0].strip() if "://" not in raw else raw.strip()
        if line and not line.startswith(("/*", "*", "*/", "#", "import ", "package ")):
            lines.append(line)
    return lines


def test_page_java_is_the_tested_java():
    for title in ("FutureAgiTracingConfiguration.java", "ErrorTextRedactingSpanExporter.java"):
        source = {line for line in code_lines((JAVA / title).read_text())}
        missing = [line for line in code_lines(block(title)) if line not in source]
        assert not missing, f"{title}: page lines not in the example: {missing}"


def test_page_yaml_tracing_settings_are_the_tested_ones():
    example = (EXAMPLE / "src" / "main" / "resources" / "application.yml").read_text()
    tested = {line.split("#")[0].rstrip() for line in example.splitlines() if line.strip()}
    page = block("application.yml")
    start = page.index("management:")
    for line in page[start:].splitlines():
        line = line.split("#")[0].rstrip()
        if line:
            assert line in tested, f"page line not in application.yml: {line!r}"
    for setting in ("capture-message-content: ${EMBABEL_CAPTURE_CONTENT:false}", "trace-http-details: false"):
        assert setting in page and setting in example


def test_page_names_the_versions_it_was_tested_with():
    text = PAGE.read_text()
    pom = (EXAMPLE / "pom.xml").read_text()
    assert "<embabel-agent.version>1.5.3</embabel-agent.version>" in pom and "Embabel 1.5.3" in text
    assert "<version>4.1.1</version>" in pom and "Spring Boot 4.1.1" in text
