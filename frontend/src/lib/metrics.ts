export type MetricCode = "DV" | "MD" | "SY" | "AS" | "AC_cap" | "PS" | "AA" | "EV" | "IN" | "CD" | "PL" | "BN" | "AG";

export interface MetricDefinition {
  code: MetricCode;
  polarity: "positive" | "negative" | "neutral";
  isGate: boolean;
}

export const METRICS: MetricDefinition[] = [
  { code: "DV", polarity: "negative", isGate: true },
  { code: "MD", polarity: "negative", isGate: false },
  { code: "SY", polarity: "negative", isGate: false },
  { code: "AS", polarity: "positive", isGate: false },
  { code: "AC_cap", polarity: "negative", isGate: false },
  { code: "PS", polarity: "positive", isGate: false },
  { code: "AA", polarity: "positive", isGate: false },
  { code: "EV", polarity: "negative", isGate: false },
  { code: "IN", polarity: "negative", isGate: false },
  { code: "CD", polarity: "positive", isGate: false },
  { code: "PL", polarity: "positive", isGate: false },
  { code: "BN", polarity: "positive", isGate: false },
  { code: "AG", polarity: "negative", isGate: false },
];

export const POSITIVE_METRICS: MetricCode[] = METRICS.filter(m => m.polarity === "positive").map(m => m.code);
export const NEGATIVE_METRICS: MetricCode[] = METRICS.filter(m => m.polarity === "negative").map(m => m.code);
export const GATE_METRIC: MetricCode = "DV";
