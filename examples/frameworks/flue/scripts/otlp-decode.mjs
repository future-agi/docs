// Minimal, dependency-free decoder for OTLP/HTTP protobuf trace requests
// (opentelemetry.proto.collector.trace.v1.ExportTraceServiceRequest).
// It reads only the fields the tests assert on.

function readVarint(buf, pos) {
  let result = 0n;
  let shift = 0n;
  for (;;) {
    if (pos >= buf.length) throw new Error("truncated varint");
    const byte = buf[pos++];
    result |= BigInt(byte & 0x7f) << shift;
    if ((byte & 0x80) === 0) return [result, pos];
    shift += 7n;
  }
}

function* fields(buf) {
  let pos = 0;
  while (pos < buf.length) {
    let key;
    [key, pos] = readVarint(buf, pos);
    const field = Number(key >> 3n);
    const wire = Number(key & 7n);
    if (wire === 0) {
      let v;
      [v, pos] = readVarint(buf, pos);
      yield { field, wire, value: v };
    } else if (wire === 1) {
      yield { field, wire, value: buf.subarray(pos, pos + 8) };
      pos += 8;
    } else if (wire === 2) {
      let len;
      [len, pos] = readVarint(buf, pos);
      const n = Number(len);
      yield { field, wire, value: buf.subarray(pos, pos + n) };
      pos += n;
    } else if (wire === 5) {
      yield { field, wire, value: buf.subarray(pos, pos + 4) };
      pos += 4;
    } else {
      throw new Error(`unsupported wire type ${wire}`);
    }
  }
}

const utf8 = (b) => Buffer.from(b).toString("utf8");
const hex = (b) => Buffer.from(b).toString("hex");
const fixed64 = (b) => Buffer.from(b).readBigUInt64LE(0);

function anyValue(buf) {
  for (const f of fields(buf)) {
    switch (f.field) {
      case 1: return utf8(f.value);
      case 2: return f.value !== 0n;
      case 3: return Number(BigInt.asIntN(64, f.value));
      case 4: return Buffer.from(f.value).readDoubleLE(0);
      case 5: { // ArrayValue
        const out = [];
        for (const g of fields(f.value)) if (g.field === 1) out.push(anyValue(g.value));
        return out;
      }
      case 6: return keyValues(f.value, 1);
      case 7: return hex(f.value);
      default: break;
    }
  }
  return null;
}

function keyValue(buf) {
  let key = "";
  let value = null;
  for (const f of fields(buf)) {
    if (f.field === 1) key = utf8(f.value);
    else if (f.field === 2) value = anyValue(f.value);
  }
  return [key, value];
}

function keyValues(buf, fieldNo) {
  const out = {};
  for (const f of fields(buf)) {
    if (f.field === fieldNo) {
      const [k, v] = keyValue(f.value);
      out[k] = v;
    }
  }
  return out;
}

function decodeStatus(buf) {
  const status = { code: 0, message: "" };
  for (const f of fields(buf)) {
    if (f.field === 2) status.message = utf8(f.value);
    else if (f.field === 3) status.code = Number(f.value);
  }
  return status;
}

function decodeEvent(buf) {
  const ev = { name: "", timeUnixNano: 0n, attributes: {} };
  const attrs = [];
  for (const f of fields(buf)) {
    if (f.field === 1) ev.timeUnixNano = fixed64(f.value);
    else if (f.field === 2) ev.name = utf8(f.value);
    else if (f.field === 3) attrs.push(f.value);
  }
  for (const a of attrs) {
    const [k, v] = keyValue(a);
    ev.attributes[k] = v;
  }
  return ev;
}

function decodeSpan(buf) {
  const span = {
    traceId: "", spanId: "", parentSpanId: "", name: "", kind: 0,
    startTimeUnixNano: 0n, endTimeUnixNano: 0n, attributes: {}, events: [], status: { code: 0, message: "" },
  };
  for (const f of fields(buf)) {
    switch (f.field) {
      case 1: span.traceId = hex(f.value); break;
      case 2: span.spanId = hex(f.value); break;
      case 4: span.parentSpanId = hex(f.value); break;
      case 5: span.name = utf8(f.value); break;
      case 6: span.kind = Number(f.value); break;
      case 7: span.startTimeUnixNano = fixed64(f.value); break;
      case 8: span.endTimeUnixNano = fixed64(f.value); break;
      case 9: { const [k, v] = keyValue(f.value); span.attributes[k] = v; break; }
      case 11: span.events.push(decodeEvent(f.value)); break;
      case 15: span.status = decodeStatus(f.value); break;
      default: break;
    }
  }
  return span;
}

function decodeScope(buf) {
  const scope = { name: "", version: "" };
  for (const f of fields(buf)) {
    if (f.field === 1) scope.name = utf8(f.value);
    else if (f.field === 2) scope.version = utf8(f.value);
  }
  return scope;
}

/** Decode an ExportTraceServiceRequest into flat span records. */
export function decodeTraceRequest(body) {
  const buf = body instanceof Uint8Array ? body : new Uint8Array(body);
  const spans = [];
  for (const rs of fields(buf)) {
    if (rs.field !== 1) continue;
    let resource = {};
    const scopeSpans = [];
    for (const f of fields(rs.value)) {
      if (f.field === 1) resource = keyValues(f.value, 1);
      else if (f.field === 2) scopeSpans.push(f.value);
    }
    for (const ss of scopeSpans) {
      let scope = { name: "", version: "" };
      const raw = [];
      for (const f of fields(ss)) {
        if (f.field === 1) scope = decodeScope(f.value);
        else if (f.field === 2) raw.push(f.value);
      }
      for (const s of raw) spans.push({ resource, scope, ...decodeSpan(s) });
    }
  }
  return spans;
}
