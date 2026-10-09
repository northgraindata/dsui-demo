import { definePlugin } from "@northgraindata/dsui-plugin-sdk";
import {
  Card,
  PageHeader,
  Section,
} from "@northgraindata/dsui-adapter-sdk";
import { z } from "zod";

/**
 * A guided tour of the demo, built entirely from existing primitives.
 *
 * No new host API: the page is a plugin page, the persistent widget is a slot
 * contribution, and every step links to a real service route so the host's own
 * navigation does the work.
 *
 * The tour is deliberately not autoplaying. Someone who opened a public demo has
 * already decided to look, and walking them through it automatically would take
 * that away and hide the parts they came for. Every step waits for a click.
 *
 * Literal prose lives in component descriptions rather than in a text primitive,
 * because the adapter SDK has no one: `Value` binds to a resource rather than
 * printing a string.
 */

const configSchema = z.object({
  title: z.string().default("A tour of the demo"),
  disclaimer: z
    .string()
    .default(
      "Every service, row and number here is synthetic. Nothing you do reaches a real system, and the data resets on a schedule.",
    ),
});

export type Step = {
  readonly id: string;
  readonly title: string;
  readonly body: string;
  /** Where the step sends the visitor. */
  readonly path: string;
  readonly label: string;
  readonly lookFor: string;
};

/**
 * Written against the services this demo configures, in the order the narrative
 * runs: landing files, orchestration, the warehouse, the published snapshot, and
 * finally the reconciliation that ties every source together.
 */
export const STEPS: readonly Step[] = [
  {
    id: "files",
    title: "Start with the files",
    body: "Everything downstream came from here. The landing bucket holds raw CSV exactly as it arrived, which is to say not quite clean: five date formats, decorated amounts, a few rows that reference nothing.",
    path: "/services/landing",
    label: "Open object storage",
    lookFor: "A CSV whose dates are not all in the same format. That is deliberate.",
  },
  {
    id: "warehouse",
    title: "Something loads them",
    body: "PostgreSQL holds the raw layer and the transformed marts side by side. Query it yourself: this is a real database with a real statement timeout.",
    path: "/services/analytics",
    label: "Open the warehouse",
    lookFor: "A schema list, and a query you can run and edit.",
  },
  {
    id: "snapshot",
    title: "The snapshot you are reading",
    body: "One DuckDB file holds landing, staging and marts together, replaced atomically after each build. You are reading a consistent snapshot, not a live warehouse.",
    path: "/services/snapshot",
    label: "Open the snapshot",
    lookFor: "Three schemas, with the staging layer between the messy input and the clean output.",
  },
  {
    id: "sources",
    title: "Six sources, one business",
    body: "Stripe, PostHog, GA4, Meta Ads, Google Ads and Search Console all describe the same company, and none of them agree on the numbers.",
    path: "/services/snapshot",
    label: "Compare the sources",
    lookFor: "A revenue figure, and a different one right next to it.",
  },
  {
    id: "reconciliation",
    title: "Why they disagree",
    body: "The reconciliation model puts every claim side by side and names the largest gap in plain language. This is the stop worth your time.",
    path: "/services/snapshot",
    label: "See the reconciliation",
    lookFor: "Competing figures in one row, and a column saying which source is the outlier.",
  },
];

function stepSection(step: Step, index: number) {
  return Section({
    title: `${index + 1}. ${step.title}`,
    description: step.body,
    link: { label: step.label, path: step.path },
    content: Card({
      title: "What to look for",
      description: step.lookFor,
      variant: "subtle" as const,
    }),
  });
}

const guidePage = {
  kind: "page" as const,
  path: "/",
  render: () => [
    PageHeader({
      title: "A tour of the demo",
      description: "Five stops, in the order the data actually flows.",
    }),
    ...STEPS.map(stepSection),
  ],
};

/**
 * The sidebar widget. A slot rather than only a page, so the tour is reachable
 * from wherever the visitor already is.
 */
const sidebarSlot = {
  kind: "slot" as const,
  id: "demo-guide-sidebar",
  slot: "sidebar.profile" as const,
  order: 10,
  render: () => [
    Section({
      title: "Demo tour",
      description: "Five stops through the stack, in the order the data flows.",
      link: { label: "Start the tour", path: "/plugins/demo-guide/overview" },
      content: Card({ title: "New here?", variant: "subtle" as const }),
    }),
  ],
};

export default definePlugin({
  metadata: {
    id: "demo-guide",
    name: "Demo tour",
    version: "1.0.0",
    apiVersion: 1,
  },
  configSchema,
  setup(registry, config) {
    registry.page(guidePage, {
      id: "overview",
      title: config.title,
      description: `${STEPS.length} stops, in the order the data flows.`,
    });
    registry.navigation({
      id: "demo-guide-link",
      area: "secondary",
      label: "Demo tour",
      pageId: "overview",
      order: 50,
    });
    registry.slot(sidebarSlot);
    registry.page(
      {
        kind: "page" as const,
        path: "/about",
        render: () => [
          PageHeader({ title: "About this demo", description: config.disclaimer }),
        ],
      },
      { id: "about", title: "About this demo", description: config.disclaimer },
    );
  },
});