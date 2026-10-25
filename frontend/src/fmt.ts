export const g = (mg: number | null | undefined) =>
  mg === null || mg === undefined ? "—" : (mg / 1000).toLocaleString("en-IN", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

export const rupees = (paise: number | null | undefined) =>
  paise === null || paise === undefined
    ? "—"
    : (paise < 0 ? "−₹" : "₹") + Math.round(Math.abs(paise) / 100).toLocaleString("en-IN");

export const pct = (bp: number | null | undefined) => (bp === null || bp === undefined ? "—" : (bp / 100).toFixed(2) + "%");

export const karat = (ppt: number) =>
  ({ 999: "24K", 916: "22K", 833: "20K", 750: "18K", 585: "14K" } as Record<number, string>)[ppt] ?? `${ppt}/1000`;

export function day(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function dateTime(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "52.34" -> 52340 without floating-point error. Returns null if not a valid weight. */
export function gramsToMg(s: string): number | null {
  const t = s.trim();
  if (!/^\d+(\.\d{0,3})?$/.test(t)) return null;
  const [whole, frac = ""] = t.split(".");
  return parseInt(whole, 10) * 1000 + parseInt((frac + "000").slice(0, 3), 10);
}

export const CATEGORIES: Record<string, string> = {
  plain_bangle: "Plain bangle",
  chain: "Chain",
  filigree: "Filigree work",
  necklace_haar: "Necklace / Haar",
  ring: "Ring",
  jhumka_earring: "Jhumka / Earring",
  mangalsutra: "Mangalsutra",
  other: "Other",
};

export const KIND_LABEL: Record<string, string> = {
  ISSUE: "Gold issued",
  RETURN_PIECE: "Piece received",
  RETURN_SCRAP: "Scrap received",
  REFINER_CREDIT: "Refiner recovery",
  WASTAGE_ALLOWANCE: "Wastage allowed",
  GOLD_ADJUSTMENT: "Gold adjustment",
  MAKING_CHARGE: "Making charge",
  PAYMENT: "Payment",
  MONEY_ADJUSTMENT: "Money adjustment",
};

export const KIND_LABEL_HI: Record<string, string> = {
  ISSUE: "सोना मिला",
  RETURN_PIECE: "पीस जमा",
  RETURN_SCRAP: "स्क्रैप जमा",
  REFINER_CREDIT: "रिफाइनर से वापसी",
  WASTAGE_ALLOWANCE: "घटत छूट",
  GOLD_ADJUSTMENT: "सोना सुधार",
  MAKING_CHARGE: "मज़दूरी",
  PAYMENT: "भुगतान",
  MONEY_ADJUSTMENT: "रकम सुधार",
};
