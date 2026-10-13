import { createHash, timingSafeEqual } from "node:crypto";
import { definePlugin } from "@northgraindata/dsui-plugin-sdk";
import { z } from "zod";
import type {
  PluginAuthenticationProvider,
  PluginAuthorizationProvider,
  PluginPrincipal,
} from "@northgraindata/dsui-plugin-sdk";

/**
 * Two tiers for one public instance.
 *
 * OSS DSUI has no identity provider. With no authentication plugin installed the
 * server assigns `localPrincipalMiddleware()`, which is `owner` to every request
 * on the internet. That is correct for the single-operator install OSS targets
 * and completely wrong for a public demo, so this plugin supplies the missing
 * half: identity is a plugin concern, and here nobody signs in.
 *
 * Everyone gets `operator`. That grants reading and executing, which is what a
 * demo is for, and withholds `manage`, which is what would let a stranger change
 * configuration or delete a service. The grants are a hard ceiling in the host's
 * `auth.ts`, so no plugin can widen them back.
 *
 * The maintainer holds `adminSecret` and gets `owner`, presented either as the
 * `x-demo-admin` header or as a cookie. The comparison is constant-time, and the
 * secret is compared after hashing so the comparison is not short-circuited by
 * length.
 */

const COOKIE_NAME = "dsui_demo_admin";
const VISITOR_COOKIE_NAME = "dsui_demo_visitor";
const VISITOR_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ACTIONS_PER_MINUTE = 10;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * Constant-time comparison that does not leak the secret's length.
 *
 * Both sides are hashed first, so `timingSafeEqual` always sees equal-length
 * buffers and cannot short-circuit, and an empty configured secret can never
 * match.
 */
function secretMatches(presented: string, expected: string): boolean {
  if (!expected) return false;
  const digest = (value: string) =>
    createHash("sha256").update(value, "utf8").digest();
  return timingSafeEqual(digest(presented), digest(expected));
}

function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) {
      try {
        return decodeURIComponent(rest.join("="));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** Give each browser its own agent storage namespace without collecting identity. */
function visitorPrincipalId(request: Request): string {
  const visitorId = readCookie(
    request.headers.get("cookie"),
    VISITOR_COOKIE_NAME,
  );
  // The app creates this cookie before making API calls. A caller without one
  // gets a fresh identity per request, so direct API requests cannot fall back
  // to a shared anonymous chat history.
  const identity = visitorId && VISITOR_ID_PATTERN.test(visitorId)
    ? visitorId
    : crypto.randomUUID();
  const digest = createHash("sha256").update(identity, "utf8").digest("hex");
  return `demo-visitor-${digest}`;
}

const configSchema = z.object({
  /** When empty, every visitor is `operator` and nobody can reach `owner`. */
  adminSecret: z.string().default(""),
  /**
   * Visitors may run actions: queries, DAG triggers, dbt builds. Turning this
   * off drops them to `viewer`, which is genuinely read-only but also removes
   * the ability to run a query, and running a query is the demo.
   */
  allowExecution: z.boolean().default(true),
});

export default definePlugin({
  metadata: {
    id: "demo-auth",
    name: "Demo access",
    version: "1.0.0",
    apiVersion: 1,
    // Required by the host for any plugin that registers authentication, and
    // the config must mark it `critical: true` or installation is refused.
    security: true,
  },
  configSchema,
  setup(registry, config) {
    const actionRequests = new Map<string, number[]>();
    const provider: PluginAuthenticationProvider = {
      authenticate(request): PluginPrincipal {
        const presented =
          request.headers.get("x-demo-admin") ??
          readCookie(request.headers.get("cookie"), COOKIE_NAME);

        if (presented && secretMatches(presented, config.adminSecret)) {
          return { id: "demo-owner", role: "owner" };
        }

        return {
          id: visitorPrincipalId(request),
          role: config.allowExecution ? "operator" : "viewer",
          attributes: { demo: true },
        };
      },
    };

    registry.authentication(provider);
    const authorization: PluginAuthorizationProvider = {
      authorize({ principal, permission, resource }) {
        if (principal.id === "demo-owner") return true;
        if (permission !== "execute") return true;
        if (resource?.type !== "service") return false;
        // Public visitors can run the read-only source query and the demo DAG.
        // Every other action, including DuckDB and S3 mutations, stays private.
        const actionInput = resource.actionInput;
        const triggerInputIsSafe =
          isRecord(actionInput) &&
          Object.keys(actionInput).every(
            (key) => key === "dagId" || key === "conf",
          ) &&
          typeof actionInput.dagId === "string" &&
          ["demo_pipeline", "daily_ecommerce_load"].includes(actionInput.dagId) &&
          (actionInput.conf === undefined ||
            (isRecord(actionInput.conf) &&
              Object.keys(actionInput.conf).length === 0));
        const allowedAction =
          (resource.id === "analytics" && resource.actionId === "run-query") ||
          (resource.id === "orchestration" &&
            resource.actionId === "trigger-dag" &&
            triggerInputIsSafe);
        if (!allowedAction) return false;

        const now = Date.now();
        const recent = (actionRequests.get(principal.id) ?? []).filter(
          (timestamp) => now - timestamp < 60_000,
        );
        if (recent.length >= ACTIONS_PER_MINUTE) return false;
        recent.push(now);
        while (actionRequests.size >= 10_000) {
          const oldest = actionRequests.keys().next().value;
          if (!oldest) break;
          actionRequests.delete(oldest);
        }
        actionRequests.set(principal.id, recent);
        return true;
      },
    };
    registry.authorization(authorization);
  },
});
