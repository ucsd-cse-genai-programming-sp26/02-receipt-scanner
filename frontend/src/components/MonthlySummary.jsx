import { useEffect, useMemo, useState } from "react";

const DEFAULT_CATEGORIES = [
  "Groceries",
  "Beverages",
  "Dairy",
  "Snacks",
  "Personal Care",
  "Household",
  "Electronics",
  "Clothing",
  "Dining",
  "Entertainment",
  "Other",
];

function currentMonth() {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${mm}`;
}

export default function MonthlySummary({ apiFetch, refreshKey }) {
  const [month, setMonth] = useState(currentMonth());
  const [summary, setSummary] = useState([]);
  const [totals, setTotals] = useState({ spent: 0, budget: 0, remaining: 0 });
  const [budgets, setBudgets] = useState({});
  const [saving, setSaving] = useState(false);

  const rows = useMemo(() => {
    const combined = new Map();
    DEFAULT_CATEGORIES.forEach((cat) => combined.set(cat, { category: cat, spent: 0, budget: 0 }));
    summary.forEach((row) => combined.set(row.category, row));
    return [...combined.values()];
  }, [summary]);

  async function fetchSummary() {
    const res = await apiFetch(`/api/stats/monthly-summary?month=${month}`);
    if (!res.ok) return;
    const data = await res.json();
    setSummary(data.categories || []);
    setTotals(data.totals || { spent: 0, budget: 0, remaining: 0 });

    const budgetRes = await apiFetch(`/api/budgets/${month}`);
    if (budgetRes.ok) {
      const budgetData = await budgetRes.json();
      setBudgets(budgetData.budgets || {});
    }
  }

  useEffect(() => {
    fetchSummary();
  }, [month, refreshKey]);

  function updateBudget(category, value) {
    setBudgets((prev) => ({ ...prev, [category]: value }));
  }

  async function saveBudgets() {
    setSaving(true);
    const payload = {};
    for (const [category, value] of Object.entries(budgets)) {
      const parsed = parseFloat(value);
      payload[category] = Number.isFinite(parsed) ? parsed : 0;
    }

    const res = await apiFetch(`/api/budgets/${month}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ budgets: payload }),
    });

    if (res.ok) {
      await fetchSummary();
    }
    setSaving(false);
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-bold text-gray-800">Monthly Budget Summary</h2>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-sm"
        />
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Spent <span className="font-semibold text-gray-700">${totals.spent.toFixed(2)}</span>
        {" "}of <span className="font-semibold text-gray-700">${totals.budget.toFixed(2)}</span> budget this month.
      </p>

      <div className="space-y-3">
        {rows.map((row) => {
          const budget = parseFloat(budgets[row.category] ?? row.budget ?? 0) || 0;
          const spent = parseFloat(row.spent || 0);
          const percent = budget > 0 ? Math.min((spent / budget) * 100, 100) : 0;
          const withinBudget = budget <= 0 || spent <= budget;

          return (
            <div key={row.category} className="border border-gray-100 rounded-lg p-3">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div>
                  <p className="font-medium text-gray-800 text-sm">{row.category}</p>
                  <p className="text-xs text-gray-500">
                    Spent ${spent.toFixed(2)} / Budget ${budget.toFixed(2)}
                  </p>
                </div>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={budgets[row.category] ?? row.budget ?? ""}
                  onChange={(e) => updateBudget(row.category, e.target.value)}
                  className="w-28 border border-gray-300 rounded px-2 py-1 text-sm text-right"
                  placeholder="0.00"
                />
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full ${withinBudget ? "bg-green-500" : "bg-red-500"}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={saveBudgets}
        disabled={saving}
        className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-60"
      >
        {saving ? "Saving..." : "Save Budgets"}
      </button>
    </div>
  );
}
