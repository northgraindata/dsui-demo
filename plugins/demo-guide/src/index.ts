import {
	Button,
	Card,
	CodeBlock,
	Flex,
	type PageNode,
} from "@northgraindata/dsui-adapter-sdk";
import { definePlugin, defineSlot } from "@northgraindata/dsui-plugin-sdk";
import { z } from "zod";

const configSchema = z.object({
	title: z.string().default("Debug your data stack · 6–8 minutes"),
	disclaimer: z
		.string()
		.default(
			"Synthetic demo data. The repair runs in an isolated, disposable database.",
		),
});

export const REPORT_SQL = `-- A daily report with a suspicious drop in successful orders.
SELECT d.ordered_on, count(o.order_id) AS reported_orders,
       coalesce(sum(o.amount), 0) AS revenue
FROM (SELECT DISTINCT ordered_on FROM landing.demo_tour_orders) d
LEFT JOIN marts.fct_tour_orders o USING (ordered_on)
GROUP BY d.ordered_on ORDER BY d.ordered_on;`;
export const SOURCE_SQL = `-- Inspect the same orders at their operational source.
SELECT ordered_on, status, count(*) AS orders, sum(amount) AS revenue
FROM raw.demo_tour_orders
GROUP BY ordered_on, status ORDER BY ordered_on, status;`;
export const VERIFY_SQL = `-- Test the hypothesis against the actual landed input.
SELECT ordered_on,
       count(*) FILTER (WHERE status = 'paid') AS old_filter,
       count(*) FILTER (WHERE status IN ('paid', 'completed')) AS corrected_filter,
       sum(amount) FILTER (WHERE status IN ('paid', 'completed')) AS revenue
FROM landing.demo_tour_orders GROUP BY ordered_on ORDER BY ordered_on;`;
const queryPath = (service: string, sql: string) =>
	`/services/${service}/query?sql=${encodeURIComponent(sql)}`;

export type Step = {
	readonly id: string;
	readonly title: string;
	readonly minutes: number;
	readonly body: string;
	readonly path: string;
	readonly target: string;
	readonly runNext?: string;
	readonly repair?: boolean;
	readonly code?: string;
};

/** One investigation, grouped by screen so results remain visible between steps. */
export const STEPS: readonly Step[] = [
	{
		id: "welcome",
		title: "Your data stack, one workspace",
		minutes: 0.25,
		body: "Explore how DSUI brings your databases, pipelines and code together. In 6–8 minutes, you’ll investigate a broken report using the real tools, then see how to extend the workspace with your own plugin.",
		path: "/",
		target: "dashboard.services",
	},
	{
		id: "workspace",
		title: "Your stack, in one workspace",
		minutes: 0.5,
		body: "Each card is a configured connection. PostgreSQL is the operational source; DuckDB is the analytics warehouse. Adapters expose each system’s own pages, resources and actions in this shared UI. Choose a service without losing the rest of the stack.",
		path: "/",
		target: "dashboard.service.snapshot",
	},
	{
		id: "ui",
		title: "How to move around",
		minutes: 0.5,
		body: "The workspace header identifies the connection. Its tabs come from the adapter: browse data, run SQL and inspect history. This tour is a plugin contribution above the real application; the same surfaces remain usable while it is open.",
		path: "/services/snapshot/query",
		target: "service.workspace.navigation",
	},
	{
		id: "report",
		title: "Run the report that raised the alert",
		minutes: 0.5,
		body: "This prepared query reads a real dbt mart. Click Run in the highlighted editor. The guide will advance only after the query succeeds; you can edit the SQL and rerun it yourself.",
		path: queryPath("snapshot", REPORT_SQL),
		target: "query.editor",
		runNext: "report-result",
	},
	{
		id: "report-result",
		title: "Three orders become zero",
		minutes: 0.5,
		body: "The report falls from 3 orders and 300 revenue to 1 and 90, then zero. A successful SQL statement does not prove the numbers are right. Next, inspect the records at their source before blaming the warehouse.",
		path: queryPath("snapshot", REPORT_SQL),
		target: "query.results",
	},
	{
		id: "source",
		title: "Check PostgreSQL, not a second dashboard",
		minutes: 0.5,
		body: "Run the source query. The PostgreSQL adapter uses a bounded, read-only connection here. We are inspecting the same nine tour orders, kept separate from the larger generated dataset.",
		path: queryPath("analytics", SOURCE_SQL),
		target: "query.editor",
		runNext: "source-result",
	},
	{
		id: "source-result",
		title: "The orders exist. Their status changed",
		minutes: 0.5,
		body: "There are still three successful orders each day. On October 9, completed appears alongside paid; on October 10 it replaces it. We have a concrete hypothesis: a transformation still accepts only the old status.",
		path: queryPath("analytics", SOURCE_SQL),
		target: "query.results",
	},
	{
		id: "model",
		title: "Find the assumption in the dbt model",
		minutes: 0.75,
		body: "The dbt adapter exposes the model source and dependencies. This model reads landing.demo_tour_orders, then filters WHERE status = 'paid'. That line silently drops completed orders. The bug is deliberately confined to this tour model.",
		path: "/services/transformations/models/model.dsui_demo.fct_tour_orders",
		target: "dbt.model.source",
	},
	{
		id: "pipeline",
		title: "A green pipeline can publish wrong numbers",
		minutes: 0.5,
		body: "Open demo_pipeline to inspect its actual task graph and run history: extract, build and publish. Those tasks can succeed while a SQL filter excludes valid business records. DSUI gives you execution context alongside the data; task success and data correctness are separate checks.",
		path: "/services/orchestration/dags/demo_pipeline?tab=graph",
		target: "airflow.dag.graph",
	},
	{
		id: "landing",
		title: "Check the input boundary",
		minutes: 0.5,
		body: "The landing bucket contains demo_tour_orders.parquet, extracted from PostgreSQL and published by the same pipeline. The highlighted row shows its size, format and modification time. Keeping input artifacts makes it possible to distinguish an extraction problem from a model problem.",
		path: "/services/landing/buckets/landing",
		target: "s3.object.demo_tour_orders.parquet",
	},
	{
		id: "verify",
		title: "Prove the corrected predicate",
		minutes: 0.5,
		body: "Back in DuckDB, compare the old filter with paid OR completed on the landed records. Run the query. This checks the hypothesis against the input before changing any production-like mart.",
		path: queryPath("snapshot", VERIFY_SQL),
		target: "query.editor",
		runNext: "repair",
	},
	{
		id: "repair",
		title: "Test the fix in an isolated dbt build",
		minutes: 0.75,
		body: "The corrected filter restores 3 orders and 300 revenue every day. Now build the corrected model and run its regression test in a disposable database. The test requires nine orders and 900 total revenue. This action rebuilds only a tiny plugin-owned project.",
		path: queryPath("snapshot", VERIFY_SQL),
		target: "query.results",
		repair: true,
	},
	{
		id: "fixed",
		title: "The repair built and the regression test passed",
		minutes: 0.25,
		body: "dbt built the corrected model and verified all nine orders and 900 revenue. The disposable database has been removed; the original mart remains available so the next visitor can reproduce the same issue. You followed source → model → run → input → verified fix in one workspace.",
		path: queryPath("snapshot", VERIFY_SQL),
		target: "query.results",
	},
	{
		id: "plugins",
		title: "Extend the workspace around your tools",
		minutes: 0.5,
		body: "The code-repository plugin adds source-code context beside Airflow. It owns its code and contributes through published slots. This guide uses the same Plugin SDK: a sidebar launcher and overlay contributions. Your team can add runbooks, ownership or review workflows this way.",
		path: "/plugins/code-repository/overview",
		target: "app.content",
	},
	{
		id: "build",
		title: "Build the missing piece of your stack",
		minutes: 0.5,
		body: "Use Adapter SDK to expose a system’s connections, resources, actions and pages. Use Plugin SDK to add behavior across the workspace through published extension points. The host handles rendering and positioning; your extension owns its logic. Explore the live screens, then build an adapter or plugin for your team.",
		path: "/plugins/code-repository/overview",
		target: "app.content",
		code: `// Plugin SDK: contribute to a published host surface.
registry.slot(defineSlot({
  id: 'runbook', slot: 'service.workspace.after-header',
  render: () => Card({
    title: 'Team runbook', description: 'Deploy, debug and recover.',
  }),
}));`,
	},
];

export function stepPresentation(step: Step) {
	return { path: step.path, target: step.target };
}
function renderStep(step: Step, index: number) {
	const controls: PageNode[] = [];
	const previous = STEPS[index - 1];
	const next = STEPS[index + 1];
	if (previous)
		controls.push(
			Button({
				label: "← Back",
				overlay: `tour-${previous.id}`,
				variant: "secondary",
			}),
		);
	if (step.repair)
		controls.push(
			Button({
				label: "Build & test the isolated fix",
				action: { actionId: "repair", input: {} },
				successOverlay: "tour-fixed",
				variant: "primary",
			}),
		);
	else if (next && !step.runNext)
		controls.push(
			Button({
				label: index === 0 ? "Explore DSUI →" : "Next →",
				overlay: `tour-${next.id}`,
				variant: "primary",
			}),
		);
	return [
		Card({
			title: step.title,
			description: step.body,
			badge: `${index + 1} / ${STEPS.length}`,
			variant: "subtle",
			content: [
				...(step.code
					? [
							CodeBlock({
								label: "Your own plugin",
								value: step.code,
								language: "text",
							}),
						]
					: []),
				Flex({ content: controls, gap: "sm", wrap: true }),
			],
		}),
	];
}

export default definePlugin({
	metadata: {
		id: "demo-guide",
		name: "Demo guide",
		version: "1.0.0",
		apiVersion: 1,
	},
	configSchema,
	setup(registry) {
		registry.procedure({
			id: "repair",
			input: z.object({}),
			permission: "execute",
			handler: async () => {
				const process = Bun.spawn(
					["/opt/dbt/bin/python", "/app/plugins/demo-guide/lab/repair.py"],
					{ stdout: "pipe", stderr: "pipe" },
				);
				const [stdout, stderr, exitCode] = await Promise.all([
					new Response(process.stdout).text(),
					new Response(process.stderr).text(),
					process.exited,
				]);
				if (exitCode !== 0) {
					// Plugin errors are intentionally generic at the public API boundary.
					// Keep the isolated dbt failure diagnosable in the app's server logs.
					console.error("Demo guide repair dbt build failed", {
						exitCode,
						stdout: stdout.slice(-2000),
						stderr: stderr.slice(-1000),
					});
					throw new Error(stderr.trim() || "The isolated repair failed");
				}
				return z
					.object({
						orders: z.literal(9),
						revenue: z.literal(900),
						tests: z.literal("passed"),
						isolated: z.literal(true),
					})
					.parse(JSON.parse(stdout));
			},
		});
		registry.slot(
			defineSlot({
				id: "demo-guide-sidebar",
				slot: "sidebar.profile",
				order: 10,
				render: () =>
					Button({
						label: "Start demo tour",
						overlay: "tour-welcome",
						variant: "secondary",
					}),
			}),
		);
		STEPS.forEach((step, index) =>
			registry.slot(
				defineSlot({
					id: `tour-${step.id}`,
					slot: "overlay",
					order: index,
					presentation: {
						mode: "anchored",
						...stepPresentation(step),
						highlight: true,
						dock: "bottom-right",
						label: "Developer tour",
						...(step.runNext
							? {
									advanceOn: {
										serviceId: step.path.split("/")[2],
										target: "query.results",
										event: "success",
										overlay: `tour-${step.runNext}`,
									},
								}
							: {}),
					},
					render: () => renderStep(step, index),
				}),
			),
		);
	},
});
