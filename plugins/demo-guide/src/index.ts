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
	readonly next?: string;
	readonly starts?: readonly { readonly label: string; readonly step: string }[];
	readonly sdk?: readonly string[];
	readonly sdkFor?: string;
	readonly code?: string;
	readonly codeLabel?: string;
	readonly githubStar?: boolean;
};

/** Short product tours, with optional SDK examples beside the first real example. */
export const STEPS: readonly Step[] = [
	{
		id: "home-start",
		title: "Your services in one place",
		body: "These cards show the systems connected to this demo. Open a service to see the pages and tools its adapter provides.",
		path: "/",
		target: "dashboard.services",
		next: "home-health-slot",
	},
	{
		id: "home-health-slot",
		title: "Plugins can add to shared pages",
		body: "The health score on a service card comes from the Health plugin. It adds this small gauge in a dashboard slot that DSUI makes available to plugins.",
		path: "/",
		target: "dashboard.service.snapshot",
		sdk: ["health-plugin-config-sdk", "plugin-authoring-sdk"],
		next: "home-services",
	},
	{
		id: "home-services",
		title: "Choose what to explore",
		body: "Choose a service to see its main pages and tools. Each service tour follows the screens you can use there. SDK examples are optional if you want to see how a page is built.",
		path: "/",
		target: "dashboard.services",
		starts: [
			{ label: "Explore dbt →", step: "dbt-overview" },
			{ label: "Explore DuckDB →", step: "duckdb-overview" },
			{ label: "Explore PostgreSQL →", step: "postgres-overview" },
			{ label: "Explore Airflow →", step: "airflow-overview" },
			{ label: "Explore storage →", step: "storage-overview" },
		],
		next: "dsui-value",
	},
	{
		id: "health-plugin-config-sdk",
		title: "Add a plugin from GitHub",
		body: "Plugins can be loaded from a GitHub repository and configured in dsui.yaml. The Health plugin adds a service score to the dashboard. Set enabled to false to pause it, or remove its entry to disconnect it.",
		path: "/",
		target: "dashboard.service.snapshot",
		code: `health:\n  source: git\n  repository: northgraindata/dsui\n  ref: d765fa3a87d489f14da54abd67f3b8c39e6515e8\n  path: packages/plugin-health\n  config:\n    timeoutMs: 5000\n\n# To pause it later:\n# health:\n#   enabled: false`,
		codeLabel: "dsui.yaml",
		sdkFor: "home-health-slot",
	},
	{
		id: "dbt-overview",
		title: "Your dbt project",
		body: "This workspace brings the project’s pages into DSUI. Use the navigation to browse models, check their dependencies and review recent runs.",
		path: "/services/transformations",
		target: "service.workspace.header",
		sdk: ["dbt-page-sdk", "dbt-action-sdk"],
		next: "dbt-navigation",
	},
	{
		id: "dbt-page-sdk",
		title: "A page built with the Adapter SDK",
		body: "This page was built with just a few lines of ready-made components from the DSUI Adapter SDK.",
		path: "/services/transformations",
		target: "service.workspace.content",
		code: `export const modelsPage = definePage({\n  path: "/models",\n  render: () => [\n    PageHeader({ title: "Models" }),\n    Table({\n      source: models(),\n      columns: [\n        { id: "name", label: "Model" },\n        { id: "materialized", label: "Materialized" },\n      ],\n    }),\n  ],\n});`,
		sdkFor: "dbt-overview",
		next: "dbt-navigation",
	},
	{
		id: "dbt-action-sdk",
		title: "An action runs a task",
		body: "The dbt overview has a Run dbt build button. The adapter defines that operation as an action and binds it to a shared Button component. DSUI handles the request and displays the result.",
		path: "/services/transformations",
		target: "service.workspace.content",
		code: `Button({\n  label: "Run dbt build",\n  action: runBuild({}),\n});`,
		codeLabel: "From the dbt adapter",
		sdkFor: "dbt-overview",
	},
	{
		id: "dbt-navigation",
		title: "Browse the project",
		body: "Choose Models in the navigation to see what dbt found in the project.",
		path: "/services/transformations",
		target: "service.workspace.navigation",
		next: "dbt-models",
	},
	{
		id: "dbt-models",
		title: "A list from the project manifest",
		body: "This table shows the models dbt found in the project. Choose one to see its SQL and the models it depends on.",
		path: "/services/transformations/models",
		target: "dbt.models.table",
		sdk: ["dbt-resource-sdk"],
		next: "dbt-model",
	},
	{
		id: "dbt-resource-sdk",
		title: "Where this table gets its data",
		body: "The adapter reads model details from dbt’s manifest through a resource named models. The page passes that resource to Table; the Adapter SDK renders the rows and provides shared table features.",
		path: "/services/transformations/models",
		target: "dbt.models.table",
		code: `const models = defineResource({\n  id: "models",\n  query: (_input, context) => readModels(context),\n});\n\nTable({\n  source: models(),\n  columns: modelColumns,\n});`,
		codeLabel: "Simplified Adapter SDK example",
		sdkFor: "dbt-models",
	},
	{
		id: "dbt-model",
		title: "Inspect a model",
		body: "The model page shows its SQL and dependencies together. This helps you see what the model does and which upstream models it relies on.",
		path: "/services/transformations/models/model.dsui_demo.fct_tour_orders",
		target: "dbt.model.source",
		next: "dsui-value",
	},
	{
		id: "duckdb-overview",
		title: "Run SQL against the warehouse",
		body: "Use this page to ask questions of the data in DuckDB. The query editor and results stay together, so it is easy to change a query and compare the output.",
		path: "/services/snapshot/query",
		target: "query.editor",
		sdk: ["duckdb-query-sdk"],
		next: "dsui-value",
	},
	{
		id: "duckdb-query-sdk",
		title: "A query page from the SDK",
		body: "The Adapter SDK provides the query editor and results view. An adapter supplies the connection and query action; the shared components handle the interface.",
		path: "/services/snapshot/query",
		target: "query.results",
		code: `QueryEditor({\n  language: "sql",\n  action: runQuery,\n  explorer: { source: databases() },\n});`,
		sdkFor: "duckdb-overview",
	},
	{
		id: "postgres-overview",
		title: "Browse the source data",
		body: "PostgreSQL is where this demo’s operational data starts. Open a table to inspect its columns and rows before data moves into the warehouse.",
		path: "/services/analytics",
		target: "service.workspace.header",
		next: "dsui-value",
	},
	{
		id: "airflow-overview",
		title: "See how a workflow ran",
		body: "Open a workflow to see its tasks, their order and the result of each task. A successful task means that step ran; check the data too to confirm the result is useful.",
		path: "/services/orchestration",
		target: "service.workspace.navigation",
		next: "airflow-graph",
	},
	{
		id: "airflow-graph",
		title: "Follow the task graph",
		body: "The graph shows which tasks depend on each other and how the selected run finished. Red tasks indicate a failed step; open one to see its logs and details.",
		path: "/services/orchestration/dags/demo_pipeline?tab=graph",
		target: "airflow.dag.graph",
		next: "dsui-value",
	},
	{
		id: "storage-overview",
		title: "Find the files workflows use",
		body: "Object storage holds files that workflows read or produce. Open a bucket to see the files and inspect their type, size and last update.",
		path: "/services/landing",
		target: "service.workspace.header",
		next: "storage-file",
	},
	{
		id: "storage-file",
		title: "Inspect a stored file",
		body: "Select a file to see its details. This helps you check whether the expected input or output is present before investigating a later step.",
		path: "/services/landing/buckets/landing",
		target: "s3.object.demo_tour_orders.parquet",
		next: "dsui-value",
	},
	{
		id: "dsui-value",
		title: "Make DSUI fit your work",
		body: "DSUI brings your systems together so an AI assistant can use context from across your stack. The most useful additions are the ones tailored to your team: adapters for the systems you use and plugins for your checks and workflows.",
		path: "/",
		target: "dashboard.services",
		next: "dsui-open-source",
	},
	{
		id: "dsui-open-source",
		title: "Open source, ready to grow with you",
		body: "Building and maintaining all those integrations yourself can cost tens of thousands of dollars. DSUI gives you a free, open-source foundation to start from. If it looks useful, leave a star to help more builders find it.",
		path: "/",
		target: "dashboard.services",
		githubStar: true,
	},
	{
		id: "plugin-authoring-sdk",
		title: "A small plugin can add a slot",
		body: "A plugin can add its own content at a place DSUI exposes. This example adds a badge to dashboard service cards, like the Health plugin adds a gauge. DSUI keeps the page layout; the plugin supplies the contribution.",
		path: "/",
		target: "dashboard.service.snapshot",
		code: `export default definePlugin({\n  metadata: { id: "hello", name: "Hello", version: "1.0.0", apiVersion: 1 },\n  setup(registry) {\n    registry.slot(defineSlot({\n      id: "hello-service-card",\n      slot: "dashboard.service-card.trailing",\n      render: () => Badge({ label: "Hello" }),\n    }));\n  },\n});`,
		codeLabel: "Plugin SDK",
		sdkFor: "home-health-slot",
	},
];

export function stepPresentation(step: Step) {
	return {
		path: step.path,
		target: step.target,
	};
}
function renderStep(step: Step) {
	const controls: PageNode[] = [];
	if (step.sdkFor) {
		controls.push(
			Button({
				label: "Continue tour →",
				overlay: `tour-${step.sdkFor}`,
				variant: "primary",
			}),
		);
	} else {
		for (const start of step.starts ?? [])
			controls.push(
				Button({
					label: start.label,
					overlay: `tour-${start.step}`,
					variant: "secondary",
				}),
			);
		for (const sdkStep of step.sdk ?? [])
			controls.push(
				Button({
					label:
						sdkStep === "health-plugin-config-sdk"
							? "See the plugin config"
							: sdkStep === "plugin-authoring-sdk"
								? "Create a plugin"
								: sdkStep === "dbt-action-sdk"
									? "See the action"
									: "See how this works",
					overlay: `tour-${sdkStep}`,
					variant: "secondary",
				}),
			);
		if (step.next)
			controls.push(
				Button({
					label: "Next →",
					overlay: `tour-${step.next}`,
					variant: "primary",
				}),
			);
	}
	return [
		Card({
			title: step.title,
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
		STEPS.forEach((step) =>
			registry.slot(
				defineSlot({
					id: `tour-${step.id}`,
					slot: "overlay",
					order: STEPS.indexOf(step),
					presentation: {
						mode: "anchored",
						...stepPresentation(step),
						highlight: true,
						dock: "bottom-right",
						label: "DSUI tour",
					},
					render: () => renderStep(step),
				}),
			),
		);
	},
});
