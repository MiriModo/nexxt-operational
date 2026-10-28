/** Payment categories (as in the bank's app): English name and a chart colour class (see .hbars .b i.*). */
export const CATEGORIES: Record<string, { name: string; kind: string }> = {
  groceries: { name: "Groceries", kind: "brand" },
  restaurants: { name: "Restaurants", kind: "warn" },
  appliances_it: { name: "Appliances & IT", kind: "" },
  shopping: { name: "Shopping", kind: "" },
  home_diy: { name: "Home & DIY", kind: "" },
  transport: { name: "Transport", kind: "" },
  health: { name: "Health", kind: "ok" },
  entertainment: { name: "Entertainment", kind: "warn" },
  services: { name: "Services", kind: "" },
  travel: { name: "Travel", kind: "" },
  utilities_bills: { name: "Utilities & bills", kind: "brand" },
  housing: { name: "Housing (rent)", kind: "brand" },
  loan_payments: { name: "Loan payments, other banks", kind: "err" },
  cash: { name: "Cash withdrawals", kind: "mute" },
  legal: { name: "Garnishments", kind: "err" },
  internal_transfers: { name: "Internal transfers", kind: "mute" },
  other: { name: "Other", kind: "mute" },
  income_salary: { name: "Salary", kind: "ok" },
  income_pension: { name: "Pension", kind: "ok" },
  income_rent: { name: "Rent received", kind: "ok" },
  income_dividends: { name: "Dividends", kind: "ok" },
  transfers_in: { name: "Transfers received", kind: "mute" },
};

export const categoryName = (id: string) => CATEGORIES[id]?.name ?? id.replace(/_/g, " ");
