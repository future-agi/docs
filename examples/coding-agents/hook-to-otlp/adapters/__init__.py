"""Per-app adapters for the hook-to-OTLP emitter.

Each module in this package maps one coding agent's hook payloads onto the
normalized ``SpanEvent`` records defined in ``adapters.base``. ``emit.py``
loads an adapter by its module name (``python3 emit.py cursor`` imports
``adapters.cursor``).
"""
