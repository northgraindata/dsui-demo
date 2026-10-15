import { describe, expect, test } from "bun:test";
import plugin, { renderStep, STEPS, stepPresentation } from "./index.js";

function overlayLinks(value: unknown): string[] {
	if (Array.isArray(value)) return value.flatMap(overlayLinks);
	if (typeof value !== "object" || value === null) return [];
	return Object.entries(value).flatMap(([key, child]) =>
		key === "overlay" && typeof child === "string"
			? [child]
			: overlayLinks(child),
	);
}

describe("linear demo guide", () => {
	test("navigation visits every step in order without branches", () => {
		for (const [index, step] of STEPS.entries()) {
			const expected = [STEPS[index - 1], STEPS[index + 1]]
				.filter((adjacent) => adjacent !== undefined)
				.map((adjacent) => `tour-${adjacent.id}`);
			expect(overlayLinks(renderStep(step))).toEqual(expected);
		}
		expect(STEPS[0]?.id).toBe("home-start");
		expect(STEPS.at(-1)?.githubStar).toBe(true);
		expect(plugin.metadata.security).toBeUndefined();
	});
	test("SDK steps immediately follow the interface they explain", () => {
		for (const [product, sdk] of [
			["duckdb-overview", "duckdb-query-sdk"],
			["dbt-models", "dbt-resource-sdk"],
			["dbt-overview", "dbt-action-sdk"],
			["home-health-slot", "plugin-authoring-sdk"],
		]) {
			const index = STEPS.findIndex((step) => step.id === product);
			expect(STEPS[index + 1]?.id).toBe(sdk);
			expect(STEPS[index + 1]?.path).toBe(STEPS[index]?.path);
			expect(STEPS[index + 1]?.code).toBeTruthy();
		}
		expect(
			STEPS.find((step) => step.id === "dbt-resource-sdk")?.code,
		).toContain("defineResource");
		expect(STEPS.find((step) => step.id === "dbt-action-sdk")?.code).toContain(
			"runBuild",
		);
		expect(
			STEPS.find((step) => step.id === "plugin-authoring-sdk")?.code,
		).toContain("dashboard.service-card.trailing");
	});
	test("Health example uses the installed bundles and shows how to disable it", () => {
		const example = STEPS.find(
			(step) => step.id === "health-plugin-config-sdk",
		)?.code;
		expect(example).toContain("package: /app/plugins/health.mjs");
		expect(example).toContain("browserBundle: /app/plugins/health.browser.mjs");
		expect(example).toContain("enabled: false");
	});
	test("overlay paths and targets are valid and ids are unique", () => {
		expect(new Set(STEPS.map((step) => step.id)).size).toBe(STEPS.length);
		for (const step of STEPS) {
			const presentation = stepPresentation(step);
			expect(presentation.path.startsWith("/")).toBe(true);
			expect(presentation.path.startsWith("//")).toBe(false);
			expect(presentation.target.length).toBeGreaterThan(0);
		}
	});
});


test("agent introduction presents capabilities and examples without sending a request", () => {
	const step = STEPS.find((entry) => entry.id === "ai-agent");
	if (!step) throw new Error("Missing agent introduction");
	expect(step.target).toBe("dashboard.services");
	expect(step.body).toContain("Cmd/Ctrl+J");
	expect(step.code).toContain("@snapshot");
	expect(step.code).toContain("@transformations");
	expect(JSON.stringify(renderStep(step))).not.toContain('"actionId"');
});
