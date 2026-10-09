import { describe, expect, test } from "bun:test";
import plugin from "./index.js";

/**
 * The security claim of this plugin is narrow and checkable: an anonymous
 * visitor gets `operator`, never `owner`, and only the configured secret reaches
 * `owner`. Both are worth asserting against the real provider rather than a
 * copy of the logic, because a refactor that reorders the branches would
 * otherwise pass review.
 */

function authenticate(
  config: { adminSecret?: string; allowExecution?: boolean },
  request: Request,
) {
  let captured: { authenticate: (request: Request) => unknown } | undefined;
  plugin.setup(
    { authentication: (provider: typeof captured) => (captured = provider) } as never,
    { adminSecret: "", allowExecution: true, ...config } as never,
  );
  if (!captured) throw new Error("plugin registered no authentication provider");
  return captured.authenticate(request);
}

const anonymous = new Request("http://demo.local/api/v1/services");

describe("demo-auth", () => {
  test("an anonymous visitor is an operator, never an owner", () => {
    const principal = authenticate({ adminSecret: "s3cr3t" }, anonymous) as {
      id: string;
      role: string;
    };
    expect(principal.role).toBe("operator");
    expect(principal.role).not.toBe("owner");
    expect(principal.id).toBe("anonymous");
  });

  test("an empty configured secret grants nobody owner", () => {
    // Otherwise an empty header would match an unset secret and hand out owner.
    const request = new Request("http://demo.local/api/v1/services", {
      headers: { "x-demo-admin": "" },
    });
    const principal = authenticate({ adminSecret: "" }, request) as { role: string };
    expect(principal.role).toBe("operator");
  });

  test("the secret in a header reaches owner", () => {
    const request = new Request("http://demo.local/api/v1/services", {
      headers: { "x-demo-admin": "s3cr3t" },
    });
    expect((authenticate({ adminSecret: "s3cr3t" }, request) as { role: string }).role).toBe(
      "owner",
    );
  });

  test("a padded secret reaches owner, because HTTP trims the header", () => {
    const request = new Request("http://demo.local/api/v1/services", {
      headers: { "x-demo-admin": " s3cr3t " },
    });
    expect(
      (authenticate({ adminSecret: "s3cr3t" }, request) as { role: string }).role,
    ).toBe("owner");
  });

  test("the secret in a cookie reaches owner", () => {
    const request = new Request("http://demo.local/api/v1/services", {
      headers: { cookie: "other=1; dsui_demo_admin=s3cr3t; another=2" },
    });
    expect((authenticate({ adminSecret: "s3cr3t" }, request) as { role: string }).role).toBe(
      "owner",
    );
  });

  test("a wrong secret stays an operator", () => {
    // Padded variants of the real secret are deliberately absent from this
    // list. The Headers implementation strips surrounding whitespace, so
    // " s3cr3t " arrives as "s3cr3t" and reaching owner for it is correct
    // rather than a bypass. There is a test below asserting exactly that, so
    // the behaviour is pinned in both directions.
    for (const wrong of ["s3cr3", "s3cr3tt", "S3CR3T", "", " a-completely-different-secret "]) {
      const request = new Request("http://demo.local/api/v1/services", {
        headers: { "x-demo-admin": wrong },
      });
      expect(
        (authenticate({ adminSecret: "s3cr3t" }, request) as { role: string }).role,
      ).toBe("operator");
    }
  });

  test("execution can be switched off to make the demo read-only", () => {
    expect(
      (authenticate({ adminSecret: "x", allowExecution: false }, anonymous) as {
        role: string;
      }).role,
    ).toBe("viewer");
  });

  test("declares itself a security plugin", () => {
    // The host refuses to install an authentication plugin without this.
    expect(plugin.metadata.security).toBe(true);
    expect(plugin.metadata.id).toBe("demo-auth");
  });
});