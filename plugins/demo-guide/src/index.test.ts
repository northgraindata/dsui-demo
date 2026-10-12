import { describe, expect, test } from "bun:test";
import plugin, { STEPS, stepPresentation } from "./index.js";

describe("contextual demo guide", () => {
	test("starts on the dashboard and links to a tour for every service", () => {
		expect(STEPS[0]?.id).toBe("home-start");
		expect(STEPS[1]?.id).toBe("home-health-slot");
		const home = STEPS.find((step) => step.id === "home-services");
		expect(home?.starts?.map((start) => start.step)).toEqual([
			"dbt-overview",
			"duckdb-overview",
			"postgres-overview",
			"airflow-overview",
			"storage-overview",
		]);
		expect(home?.next).toBe("dsui-value");
		expect(plugin.metadata.security).toBeUndefined();
	});

	test("product tours end with the shared-context and open-source message", () => {
		for (const id of [
			"dbt-model",
			"duckdb-overview",
			"postgres-overview",
			"airflow-graph",
			"storage-file",
		])
			expect(STEPS.find((step) => step.id === id)?.next).toBe("dsui-value");
		expect(STEPS.find((step) => step.id === "dsui-value")?.next).toBe(
			"dsui-open-source",
		);
		expect(STEPS.find((step) => step.id === "dsui-open-source")?.githubStar).toBe(
			true,
		);
	});

	test("SDK examples are optional branches and return to the product tour", () => {
		for (const step of STEPS.filter((candidate) => candidate.sdk)) {
			for (const sdkId of step.sdk ?? []) {
				const sdk = STEPS.find((candidate) => candidate.id === sdkId);
				expect(sdk).toBeDefined();
				expect(sdk?.sdkFor).toBe(step.id);
				expect(sdk?.code).toBeTruthy();
			}
		}
		expect(STEPS.find((step) => step.id === "dbt-resource-sdk")?.code).toContain(
			"defineResource",
		);
		expect(STEPS.find((step) => step.id === "dbt-action-sdk")?.code).toContain(
			"runBuild",
		);
		expect(
			STEPS.find((step) => step.id === "plugin-authoring-sdk")?.code,
		).toContain("dashboard.service-card.trailing");
		expect(
			STEPS.find((step) => step.id === "health-plugin-config-sdk")?.code,
		).toContain("repository: northgraindata/dsui");
		expect(
			STEPS.find((step) => step.id === "health-plugin-config-sdk")?.code,
		).toContain("enabled: false");
	});

	test("navigation references existing steps and each overlay has a path and target", () => {
		for (const step of STEPS) {
			if (step.next) expect(STEPS.some((item) => item.id === step.next)).toBe(true);
			for (const sdkId of step.sdk ?? [])
				expect(STEPS.some((item) => item.id === sdkId)).toBe(true);
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
