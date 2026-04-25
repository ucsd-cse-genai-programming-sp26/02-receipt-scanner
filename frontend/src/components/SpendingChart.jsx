import { useState, useEffect } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

const COLORS = [
  "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#6366f1", "#14b8a6", "#94a3b8",
];

export default function SpendingChart() {
  const [data, setData] = useState([]);
  const [view, setView] = useState("pie");
  const [loading, setLoading] = useState(true);

  async function fetchStats() {
    try {
      const res = await fetch("/api/stats/categories");
      if (res.ok) setData(await res.json());
    } catch (e) {
      console.error("Failed to load category stats", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchStats(); }, []);

  if (loading) return <p className="text-center text-gray-400 py-8">Loading spending data…</p>;
  if (data.length === 0) return null;

  const totalSpent = data.reduce((s, d) => s + d.totalSpent, 0);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-800">Spending by Category</h2>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          {["pie", "bar"].map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                view === v ? "bg-white shadow text-blue-600" : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {v === "pie" ? "Pie" : "Bar"}
            </button>
          ))}
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Total: <span className="font-semibold text-gray-700">${totalSpent.toFixed(2)}</span> across{" "}
        {data.reduce((s, d) => s + d.itemCount, 0)} items
      </p>

      <ResponsiveContainer width="100%" height={300}>
        {view === "pie" ? (
          <PieChart>
            <Pie
              data={data}
              dataKey="totalSpent"
              nameKey="category"
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ category, percent }) =>
                `${category} ${(percent * 100).toFixed(0)}%`
              }
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => `$${v.toFixed(2)}`} />
          </PieChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="category" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
            <Tooltip formatter={(v) => `$${v.toFixed(2)}`} />
            <Bar dataKey="totalSpent" name="Spent" radius={[4, 4, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>

      {/* Legend table */}
      <div className="mt-4 grid grid-cols-2 gap-2">
        {data.map((d, i) => (
          <div key={d.category} className="flex items-center gap-2 text-sm">
            <span
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{ backgroundColor: COLORS[i % COLORS.length] }}
            />
            <span className="text-gray-600 truncate">{d.category}</span>
            <span className="text-gray-400 ml-auto">${d.totalSpent.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
