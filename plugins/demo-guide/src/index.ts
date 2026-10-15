import {
	Button,
	Card,
	CodeBlock,
	Flex,
	Link,
	type PageNode,
} from "@northgraindata/dsui-adapter-sdk";
import { definePlugin, defineSlot } from "@northgraindata/dsui-plugin-sdk";
import { z } from "zod";

const configSchema = z.object({
	title: z.string().default("Explore the DSUI demo"),
	disclaimer: z
		.string()
		.default(
			"Synthetic demo data. This workspace does not connect to customer systems.",
		),
});

export type Step = {
	readonly id: string;
	readonly title: string;
	readonly body: string;
	readonly path: string;
	readonly target: string;
	readonly code?: string;
	readonly codeLabel?: string;
	readonly githubStar?: boolean;
};

/** One ordered tour: each SDK example follows the interface it explains. */
export const STEPS: readonly Step[] = [
	{
		id: "home-start",
		title: "Your services in one place",
		body: "These cards show the systems connected to this demo. Open a service to see the pages and tools its adapter provides.",
		path: "/",
		target: "dashboard.services",
	},
	{
		id: "duckdb-overview",
		title: "Open a connected service",
		body: "This is the DuckDB workspace. The navigation gives you access to its data, queries and other tools. Each connected service has pages provided by its adapter.",
		path: "/services/snapshot/query",
		target: "service.workspace.navigation",
	},
	{
		id: "duckdb-query-sdk",
		title: "A page built with ready-made components",
		body: "This page was created with just a few lines of ready-made components from the DSUI Adapter SDK. The adapter supplies the query action, and DSUI provides the editor and results view.",
		path: "/services/snapshot/query",
		target: "service.workspace.content",
		code: `export const queryPage = definePage({\n  path: "/query",\n  render: () => [\n    PageHeader({ title: "Query" }),\n    QueryEditor({\n      language: "sql",\n      action: runQuery,\n      explorer: { source: databases() },\n    }),\n  ],\n});`,
	},
	{
		id: "query-editor",
		title: "Ask a question of your data",
		body: "Write SQL here and run it against the demo warehouse. The results appear below the editor, so you can inspect the data without leaving DSUI. You can come back and try a query after the tour.",
		path: "/services/snapshot/query",
		target: "query.editor",
	},
	{
		id: "dbt-models",
		title: "See how your data is built",
		body: "The dbt adapter shows the models in this project. You can see how your data is prepared and open a model to inspect its SQL and dependencies.",
		path: "/services/transformations/models",
		target: "dbt.models.table",
	},
	{
		id: "dbt-resource-sdk",
		title: "Where this table gets its data",
		body: "The adapter reads model details from dbt’s manifest through a resource named models. The page passes that resource to Table; the Adapter SDK renders the rows and provides shared table features.",
		path: "/services/transformations/models",
		target: "dbt.models.table",
		code: `const models = defineResource({\n  id: "models",\n  query: (_input, context) => readModels(context),\n});\n\nTable({\n  source: models(),\n  columns: modelColumns,\n});`,
		codeLabel: "Simplified Adapter SDK example",
	},
	{
		id: "dbt-model",
		title: "Inspect a model",
		body: "The model page shows its SQL and dependencies together. This helps you see what the model does and which upstream models it relies on.",
		path: "/services/transformations/models/model.dsui_demo.fct_tour_orders",
		target: "dbt.model.source",
	},
	{
		id: "dbt-overview",
		title: "Take action from the same place",
		body: "Adapters can provide actions as well as information. The Run dbt build button runs the project build from this page. You can use it after the tour; moving to the next step does not run a build.",
		path: "/services/transformations",
		target: "service.workspace.content",
	},
	{
		id: "dbt-action-sdk",
		title: "An action runs a task",
		body: "The dbt overview has a Run dbt build button. The adapter defines that operation as an action and binds it to a shared Button component. DSUI handles the request and displays the result.",
		path: "/services/transformations",
		target: "service.workspace.content",
		code: `Button({\n  label: "Run dbt build",\n  action: runBuild({}),\n});`,
		codeLabel: "From the dbt adapter",
	},
	{
		id: "airflow-graph",
		title: "Check the pipeline",
		body: "Airflow shows the tasks in a workflow and how a run finished. Red tasks indicate a failure. You can open a task to inspect its logs and compare what happened in the pipeline with the data and models you just saw.",
		path: "/services/orchestration/dags/demo_pipeline?tab=graph",
		target: "airflow.dag.graph",
	},
	{
		id: "home-health-slot",
		title: "Plugins can add to shared pages",
		body: "The health score on a service card comes from the Health plugin. It adds this small gauge in a dashboard slot that DSUI makes available to plugins.",
		path: "/",
		target: "dashboard.service.snapshot",
	},
	{
		id: "plugin-authoring-sdk",
		title: "A small plugin can add a slot",
		body: "A plugin can add its own content at a place DSUI exposes. This example adds a badge to dashboard service cards, like the Health plugin adds a gauge. DSUI keeps the page layout; the plugin supplies the contribution.",
		path: "/",
		target: "dashboard.service.snapshot",
		code: `export default definePlugin({\n  metadata: { id: "hello", name: "Hello", version: "1.0.0", apiVersion: 1 },\n  setup(registry) {\n    registry.slot(defineSlot({\n      id: "hello-service-card",\n      slot: "dashboard.service-card.trailing",\n      render: () => Badge({ label: "Hello" }),\n    }));\n  },\n});`,
		codeLabel: "Plugin SDK",
	},
	{
		id: "health-plugin-config-sdk",
		title: "Choose which plugins you use",
		body: "This demo includes the Health plugin from the DSUI GitHub repository in its image. The configuration below enables it. Set enabled to false to switch it off, or remove the entry to disconnect it.",
		path: "/",
		target: "dashboard.service.snapshot",
		code: `health:
  package: /app/plugins/health.mjs
  browserBundle: /app/plugins/health.browser.mjs
  enabled: true
  config:
    timeoutMs: 5000

# To switch it off:
#   enabled: false`,
		codeLabel: "dsui.yaml",
	},
	{
		id: "ai-agent",
		title: "Meet DSUI Agent",
		body: "Open the agent with the sparkle button in the top bar or Cmd/Ctrl+J after closing this guide. It can discover services, inspect tables and dbt models, check health and explain results. Type @ and choose Analytics warehouse to ask about DuckDB, or dbt project to inspect a model. The examples below use their service IDs. Expand the tools used in a reply to see what the agent inspected. Nothing is sent until you submit a message; messages and retrieved data go to the configured model provider.",
		path: "/",
		target: "dashboard.services",
		codeLabel: "Things to try",
		code: "@snapshot List the tables in this DuckDB warehouse and explain what the tour dataset contains.\n\n@transformations Read fct_tour_orders and explain which statuses its SQL filter excludes.",
	},
	{
		id: "dsui-value",
		title: "Make DSUI fit your work",
		body: "DSUI brings your systems together so an AI assistant can use context from across your stack. The most useful additions are the ones tailored to your team: adapters for the systems you use and plugins for your checks and workflows.",
		path: "/",
		target: "dashboard.services",
	},
	{
		id: "dsui-open-source",
		title: "Open source, ready to grow with you",
		body: "DSUI is free and open source. You can use it, change it and build your own adapters and plugins. If you find it useful, leave a star on GitHub to help more people discover the project. This is the end of the tour; close it to explore the demo yourself.",
		path: "/",
		target: "dashboard.services",
		githubStar: true,
	},
];

export function stepPresentation(step: Step) {
	return {
		path: step.path,
		target: step.target,
	};
}
export function renderStep(step: Step) {
	const index = STEPS.indexOf(step);
	const previous = STEPS[index - 1];
	const next = STEPS[index + 1];
	const controls: PageNode[] = [];
	if (previous)
		controls.push(
			Button({
				label: "← Back",
				overlay: `tour-${previous.id}`,
				variant: "secondary",
			}),
		);
	if (next)
		controls.push(
			Button({
				label: "Next →",
				overlay: `tour-${next.id}`,
				variant: "primary",
			}),
		);
	return [
		Card({
			title: `${index + 1} / ${STEPS.length} · ${step.title}`,
			description: step.body,
			variant: "subtle",
			content: [
				...(step.code
					? [
							CodeBlock({
								label: step.codeLabel ?? "Example",
								value: step.code,
								language: "text",
							}),
						]
					: []),
				...(step.githubStar
					? [
							Card({
								title: "Leave a star ⭐",
								description: "Help DSUI reach more builders.",
								variant: "subtle",
								content: Link({
									href: "https://github.com/northgraindata/dsui",
									label: "DSUI on GitHub ↗",
									external: true,
								}),
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
						label: "Explore the demo",
						overlay: "tour-home-start",
						variant: "secondary",
					}),
			}),
		);
		for (const [index, step] of STEPS.entries()) {
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
						label: "DSUI tour",
					},
					render: () => renderStep(step),
				}),
			);
		}
	},
});
