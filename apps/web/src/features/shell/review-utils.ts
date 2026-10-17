import { humanizeLabel } from "../../lib/utils";

export function formatReviewReason(reason: string) {
  const [code, field] = reason.split(":", 2);
  if (!field) return humanizeLabel(code);
  if (code === "missing_required") return `Missing ${humanizeLabel(field)}`;
  if (code === "invalid_value") return `Check ${humanizeLabel(field)}`;
  if (code === "low_confidence") return "Low classification confidence";
  if (code === "unclassified") return "Document type not identified";
  if (code === "analysis_pending") return "Analysis pending";
  if (code === "analysis_disabled") return "Document analysis is disabled";
  if (code === "unsupported_metadata")
    return `Check ${humanizeLabel(field)} against the source`;
  if (code === "conflicting_metadata")
    return `Conflicting ${humanizeLabel(field)} values; enter the correct detail`;
  if (code === "manual_metadata_preserved")
    return "Your corrected details were kept";
  if (code === "unsupported_summary" || code === "missing_summary")
    return "Summary needs review against the source";
  if (code === "classification_disagreement" || code === "mixed_categories")
    return "Document type needs review";
  if (code === "status_change")
    return "Status change found; confirm dates in Details before enabling reminders";
  if (code === "analysis_failed")
    return "Analysis unavailable; extracted text remains searchable";
  if (code === "manual_change") return "Details changed";
  return humanizeLabel(reason);
}
