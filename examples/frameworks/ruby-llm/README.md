# RubyLLM legacy regression fixture

For application setup, use the [native RubyLLM integration guide](https://docs.futureagi.com/docs/integrations/frameworks/ruby-llm). This directory retains the old 1.x implementation for regression tests; it is not a maintained, installable integration package or a replacement for the native setup.

The earlier helper trusted entire `gen_ai.request.*`, `gen_ai.response.*` and `gen_ai.usage.*` namespaces, allowing custom attributes to export content without opt-in. The retained fixture now allows only the exact span-attribute names in `METADATA_ATTRIBUTES`. It still drops events and, in metadata-only mode, error status descriptions. This is not a secret scanner: values of allowed attributes, span names, resource attributes and other instrumentation remain application-owned. Content opt-in keeps arbitrary span attributes.

Do not remove the sanitizer from an exporting legacy installation. Follow the guide's instructions to disable legacy tracing until you can migrate to native tracing or use a maintained privacy-filtering package. This fixture does not supply that package.

## Run the regression tests

Use Ruby 3.2 or newer. The fixture covers RubyLLM 1.15.0 and 1.16.0 with third-party instrumentation 0.7.1; that instrumentation does not support RubyLLM 2.x.

```bash
bundle install
bundle exec rake test
```

Set `RUBY_LLM_VERSION=1.15.0` for the older compatibility leg. The tests use synthetic data and WebMock for both model requests and OTLP export. Native 2.1 tests live in `scripts/ruby-llm-native.test.rb` at the repository root. The historical `app.rb` and `run_e2e.sh` are not the current customer setup.
