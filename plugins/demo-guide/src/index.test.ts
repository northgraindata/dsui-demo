import { describe, expect, test } from "bun:test";
import plugin, { STEPS, stepPresentation } from "./index.js";

describe("contextual demo guide", () => {
	test("starts on the dashboard and links to a tour for every service", () => {
		expect(STEPS[0]?.id).toBe("home-start");
		const home = STEPS.find((step) => step.id === "home-services");
		expect(home?.starts?.map((start) => start.step)).toEqual([
			"dbt-overview",
			"duckdb-overview",
			"postgres-overview",
			"airflow-overview",
			"storage-overview",
		]);
		expect(plugin.metadata.security).toBeUndefined();
	});

	test("SDK examples are optional branches and return to the product tour", () => {
		for (const step of STEPS.filter((candidate) => candidate.sdk)) {
			const sdk = STEPS.find((candidate) => candidate.id === step.sdk);
			expect(sdk).toBeDefined();
			expect(sdk?.sdkFor).toBe(step.id);
			expect(sdk?.code).toBeTruthy();
		}
	});

	test("navigation references existing steps and each overlay has a path and target", () => {
		for (const step of STEPS) {
			if (step.next) expect(STEPS.some((item) => item.id === step.next)).toBe(true);
			if (step.sdk) expect(STEPS.some((item) => item.id === step.sdk)).toBe(true);
			if (step.sdkFor)
				expect(STEPS.some((item) => item.id === step.sdkFor)).toBe(true);
			for (const start of step.starts ?? [])
				expect(STEPS.some((item) => item.id === start.step)).toBe(true);
			const presentation = stepPresentation(step);
			expect(presentation.path.startsWith("/")).toBe(true);
			expect(presentation.path.startsWith("//")).toBe(false);
			expect(presentation.target.length).toBeGreaterThan(0);
		}
	});

	test("contribution ids are stable and unique", () => {
		expect(new Set(STEPS.map((step) => step.id)).size).toBe(STEPS.length);
	});
});
