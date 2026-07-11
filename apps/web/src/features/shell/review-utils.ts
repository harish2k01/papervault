import { humanizeLabel } from "../../lib/utils";

export function formatReviewReason(reason: string) {
  const [code, field] = reason.split(":", 2);
  if (!field) return humanizeLabel(code);
  if (code === "missing_required") return `Missing ${humanizeLabel(field)}`;
  if (code === "invalid_value") return `Check ${humanizeLabel(field)}`;
  if (code === "low_confidence") return "Low classification confidence";
  if (code === "unclassified") return "Document type not identified";
  if (code === "analysis_pending") return "Analysis pending";
  if (code === "manual_change") return "Details changed";
  return humanizeLabel(reason);
}
