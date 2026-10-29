import { trace } from "@opentelemetry/api";
import { ApolloServer } from "@apollo/server";

export const typeDefs = `#graphql
  type Profile { id: ID! name: String email: String }
  type Query {
    hello: String
    profile(id: ID!): Profile
    wide: Wide
    boom: String
    fail(reason: String): String
    partial: Partial
  }
  type Wide { f01: Int f02: Int f03: Int f04: Int f05: Int f06: Int f07: Int f08: Int f09: Int f10: Int
              f11: Int f12: Int f13: Int f14: Int f15: Int f16: Int f17: Int f18: Int f19: Int f20: Int }
  type Partial { ok: String bad: String }
`;

const tracer = trace.getTracer("apollo-example");

export const resolvers = {
  Query: {
    hello: () => "world",
    // A resolver that does downstream work: the active span is the graphql.resolve span, so a
    // span started here is a child of it and shares the trace id.
    profile: async (_parent, { id }) => {
      const active = trace.getActiveSpan();
      return tracer.startActiveSpan("load-profile", async (span) => {
        span.setAttribute("example.parent.name", active?.name ?? "none");
        span.end();
        return { id, name: "Ada", email: "ada@example.test" };
      });
    },
    wide: () => Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`f${String(i + 1).padStart(2, "0")}`, i + 1])),
    boom: () => {
      throw new Error("resolver failed");
    },
    // The error text echoes its argument, like real resolvers do: this is what must not reach the trace.
    fail: (_parent, { reason }) => {
      throw new Error(`failed because ${reason} at /Users/example/app/secret-path.js`);
    },
    partial: () => ({ ok: "fine" }),
  },
  Partial: {
    bad: () => {
      throw new Error("field failed");
    },
  },
};

// stopOnTerminationSignals:false - by default Apollo installs its own SIGINT/SIGTERM handler that
// stops the server and then re-raises the signal, which ends the process before an
// application handler can flush the last batch of spans. server.mjs handles the signals itself.
export const createServer = () => new ApolloServer({ typeDefs, resolvers, stopOnTerminationSignals: false });
