import { describe, expect, test } from "bun:test";
import plugin, {
	AGENT_PROMPT,
	renderStep,
	REPORT_SQL,
	SOURCE_SQL,
	STEPS,
	VERIFY_SQL,
	stepPresentation,
} from "./index.js";

describe("developer investigation", () => {
	test("introduces the UI before querying DuckDB and ends with an optional agent handoff", () => {
		expect(STEPS.slice(0, 4).map((step) => step.id)).toEqual([
			"welcome",
			"workspace",
			"ui",
			"report",
		]);
		expect(STEPS.at(-2)?.id).toBe("build");
		expect(STEPS.at(-1)?.id).toBe("agent");
		expect(
			STEPS.reduce((total, step) => total + step.minutes, 0),
		).toBeGreaterThanOrEqual(6);
		expect(
			STEPS.reduce((total, step) => total + step.minutes, 0),
		).toBeLessThanOrEqual(8);
		expect(plugin.metadata.security).toBeUndefined();
	});
	test("query steps advance to their result without navigating or losing the editor state", () => {
		for (const step of STEPS.filter((step) => step.runNext)) {
			const next = STEPS.find((candidate) => candidate.id === step.runNext);
			expect(next).toBeDefined();
			expect(next?.path).toBe(step.path);
			expect(next?.target).toBe("query.results");
		}
	});
	test("prepared queries use the actual fixture and distinguish source from warehouse", () => {
		expect(REPORT_SQL).toContain("marts.fct_tour_orders");
		expect(SOURCE_SQL).toContain("raw.demo_tour_orders");
		expect(VERIFY_SQL).toContain("'paid', 'completed'");
		for (const step of STEPS) {
			const presentation = stepPresentation(step);
			expect(presentation.path.startsWith("/")).toBe(true);
			expect(presentation.path.startsWith("//")).toBe(false);
			if (step.path.includes("?sql="))
				expect(
					new URL(step.path, "http://localhost").searchParams.get("sql"),
				).toBeTruthy();
		}
	});
	test("stable unique contributions show actual content after UI orientation", () => {
		expect(new Set(STEPS.map((step) => step.id)).size).toBe(STEPS.length);
		for (const step of STEPS.slice(3)) {
			expect(step.target).not.toContain("service.workspace.page.");
			expect(step.body.length).toBeGreaterThan(40);
		}
	});
});

describe("optional AI agent handoff", () => {
	test("ends on an existing host target without replacing the tour with a drawer", () => {
		const step = STEPS.at(-1);
		expect(step?.id).toBe("agent");
		if (!step) throw new Error("Missing agent step");
		expect(step.target).toBe("app.content");
		const previous = STEPS.at(-2);
		if (!previous) throw new Error("Missing previous step");
		expect(step.path).toBe(previous.path);
		expect(step.runNext).toBeUndefined();
		const content = JSON.stringify(renderStep(step, STEPS.length - 1, true));
		expect(content).toContain("Cmd/Ctrl+J");
		expect(content).toContain("configured model provider");
		expect(content).toContain("Things to try");
		expect(content).not.toContain('"actionId"');
		expect(AGENT_PROMPT).toContain("@transformations");
		expect(AGENT_PROMPT).toContain("fct_tour_orders");
		expect(AGENT_PROMPT).toContain("@snapshot");
		expect(AGENT_PROMPT).toContain("DuckDB");
	});
	test("offers an honest finish when the agent plugin is absent or inaccessible", () => {
		const step = STEPS.at(-1);
		if (!step) throw new Error("Missing agent step");
		const content = JSON.stringify(renderStep(step, STEPS.length - 1, false));
		expect(content).toContain("You have completed the tour");
		expect(content).toContain("not enabled or available");
		expect(content).not.toContain(AGENT_PROMPT);
		expect(content).toContain("Back");
	});
});
