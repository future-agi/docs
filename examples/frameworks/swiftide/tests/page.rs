//! The docs page shows code from this crate. Every line of a code block labelled `Cargo.toml`,
//! `src/lib.rs` or `src/main.rs` must exist in that file, so the page cannot drift from the code
//! that the tests and the end-to-end script run.

use std::path::Path;

const PAGE: &str = "../../../src/pages/docs/integrations/frameworks/swiftide.mdx";

fn blocks(page: &str) -> Vec<(String, Vec<String>)> {
    let mut out = Vec::new();
    let mut current: Option<(String, Vec<String>)> = None;
    for line in page.lines() {
        let trimmed = line.trim_start();
        if let Some(rest) = trimmed.strip_prefix("```") {
            match current.take() {
                Some(block) => out.push(block),
                None => {
                    let label = rest.split_whitespace().nth(1).unwrap_or("").to_string();
                    current = Some((label, Vec::new()));
                }
            }
        } else if let Some((_, lines)) = current.as_mut() {
            lines.push(line.to_string());
        }
    }
    out
}

#[test]
fn page_code_blocks_match_the_example() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let page = std::fs::read_to_string(root.join(PAGE)).expect("docs page next to the example");
    let mut checked = 0;
    for (label, lines) in blocks(&page) {
        if !matches!(label.as_str(), "Cargo.toml" | "src/lib.rs" | "src/main.rs") {
            continue;
        }
        let source = std::fs::read_to_string(root.join(&label)).unwrap();
        let source_lines: Vec<&str> = source.lines().map(str::trim).collect();
        for line in lines.iter().map(|l| l.trim()).filter(|l| !l.is_empty()) {
            assert!(
                source_lines.contains(&line),
                "{label}: page line not in source: {line}"
            );
            checked += 1;
        }
    }
    assert!(
        checked > 80,
        "expected the page to show the setup code, checked {checked} lines"
    );
}

#[test]
fn page_states_versions_and_defaults() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let page = std::fs::read_to_string(root.join(PAGE)).unwrap();
    let manifest = std::fs::read_to_string(root.join("Cargo.toml")).unwrap();
    for (krate, version) in [
        ("swiftide", "0.33.0"),
        ("tracing-opentelemetry", "0.34.0"),
        ("opentelemetry-otlp", "0.33.1"),
    ] {
        assert!(
            manifest.contains(&format!("{krate} = {{ version = \"={version}\""))
                || manifest.contains(&format!("{krate} = \"={version}\""))
        );
        assert!(
            page.contains(version),
            "page does not state {krate} {version}"
        );
    }
    assert!(page.contains("Content capture is **off by default**"));
    assert!(page.contains("TRACE_CONTENT=true"));
    assert!(page.contains("/tracer/v1/traces"));
}
