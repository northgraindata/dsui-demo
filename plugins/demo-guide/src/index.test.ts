import { describe, expect, test } from "bun:test";
import plugin, { STEPS } from "./index.js";

/**
 * The tour is prose pointing at service routes, which means it fails quietly: a
 * step whose path is wrong still renders, it just sends a visitor somewhere that
 * does not exist. These assertions are the cheap guard against that.
 */

describe("demo-guide", () => {
  test("step ids are unique, since the host keys routes by them", () => {
    const ids = STEPS.map((step) => step.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("every step path is absolute", () => {
    for (const step of STEPS) {
      expect(step.path.startsWith("/")).toBe(true);
    }
  });

  test("no step points at a service the demo does not configure", () => {
    // Kept in step with dsui.yaml. A mismatch renders a dead link rather than an
    // error, which is exactly the failure this catches.
    const configured = new Set(["landing", "analytics", "snapshot"]);
    for (const step of STEPS) {
      const service = step.path.split("/")[2];
      expect(configured.has(service)).toBe(true);
    }
  });

  test("every step tells the visitor what to look for", () => {
    for (const step of STEPS) {
      expect(step.body.length).toBeGreaterThan(40);
      expect(step.lookFor.length).toBeGreaterThan(20);
      expect(step.label.length).toBeGreaterThan(0);
    }
  });

  test("is not a security plugin and does not claim to be", () => {
    // Only a security plugin may publish a public page, and this one must not.
    expect(plugin.metadata.security).toBeUndefined();
  });
});