// ====== Code Summary ======
// The deployment scope's top content bar: a "Deployment ▸ {page}" breadcrumb, the page title, and a
// right-aligned primary-action slot (e.g. "+ New collection"). A thin composition over the existing
// Breadcrumb + PageHeader primitives — deployment-scope pages (Overview, Collections, Activity,
// Fleet, Settings) use this; collection-scoped pages keep their own header (CollectionShell) for now.

import type { ReactNode } from "react";
import { Breadcrumb, type BreadcrumbItem } from "./Breadcrumb";
import { PageHeader } from "../components/PageHeader";

interface TopContentBarProps {
  /** The current deployment-scope page's label — both the breadcrumb's trailing segment and title. */
  page: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function TopContentBar({ page, subtitle, actions }: TopContentBarProps) {
  const items: BreadcrumbItem[] = [
    { label: "Deployment", view: { name: "overview" } },
    { label: page },
  ];
  return (
    <PageHeader
      eyebrow={<Breadcrumb items={items} />}
      title={page}
      subtitle={subtitle}
      actions={actions}
    />
  );
}
