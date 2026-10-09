import { createHash, timingSafeEqual } from "node:crypto";
import { definePlugin } from "@northgraindata/dsui-plugin-sdk";
import { z } from "zod";
import type {
  PluginAuthenticationProvider,
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
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
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
    const provider: PluginAuthenticationProvider = {
      authenticate(request): PluginPrincipal {
        const presented =
          request.headers.get("x-demo-admin") ??
          readCookie(request.headers.get("cookie"), COOKIE_NAME);

        if (presented && secretMatches(presented, config.adminSecret)) {
          return { id: "demo-owner", role: "owner" };
        }

        return {
          id: "anonymous",
          role: config.allowExecution ? "operator" : "viewer",
          attributes: { demo: true },
        };
      },
    };

    registry.authentication(provider);
  },
});