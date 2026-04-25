import { useState } from "react";

const CATEGORIES = [
  "Groceries", "Beverages", "Dairy", "Snacks", "Personal Care",
  "Household", "Electronics", "Clothing", "Dining", "Entertainment", "Other",
];

export default function ReceiptCard({ receipt, previewUrl, onSave, onDiscard }) {
  const [items, setItems] = useState(receipt.items || []);
  const [storeName, setStoreName] = useState(receipt.storeName || "");
  const [date, setDate] = useState(receipt.date || "");
  const [tax, setTax] = useState(receipt.tax ?? "");
  const [tip, setTip] = useState(receipt.tip ?? "");
  const [showRaw, setShowRaw] = useState(false);

  const subtotal = items.reduce((sum, item) => sum + (parseFloat(item.price) || 0), 0);
  const total = subtotal + (parseFloat(tax) || 0) + (parseFloat(tip) || 0);

  function updateItem(index, field, value) {
    setItems((prev) =>
      prev.map((item, i) =>
        i === index ? { ...item, [field]: value } : item
      )
    );
  }

  function removeItem(index) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function addItem() {
    setItems((prev) => [
      ...prev,
      { id: null, name: "", price: 0, productId: null, category: "Other" },
    ]);
  }

  function handleSave() {
    onSave({
      ...receipt,
      storeName,
      date,
      subtotal: Math.round(subtotal * 100) / 100,
      tax: parseFloat(tax) || null,
      tip: parseFloat(tip) || null,
      total: Math.round(total * 100) / 100,
      items,
    });
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <input
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              className="bg-transparent text-xl font-bold text-white placeholder-blue-200 border-b border-blue-400 focus:border-white outline-none w-full"
              placeholder="Store Name"
            />
            <input
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-transparent text-sm text-blue-100 placeholder-blue-300 border-b border-transparent focus:border-blue-300 outline-none mt-1"
              placeholder="Date"
            />
          </div>
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Receipt"
              className="w-16 h-16 object-cover rounded border-2 border-white/30"
            />
          )}
        </div>
      </div>

      {/* Items */}
      <div className="px-6 py-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
            Items
          </h3>
          <span className="text-xs text-gray-400">
            {items.length} item{items.length !== 1 ? "s" : ""}
          </span>
        </div>

        {items.length === 0 && (
          <p className="text-gray-400 text-center py-4">
            No items detected. Add items manually below.
          </p>
        )}

        <div className="space-y-2">
          {items.map((item, index) => (
            <div
              key={item.id ?? `new-${index}`}
              className="flex items-center gap-2 group"
            >
              <input
                value={item.name}
                onChange={(e) => updateItem(index, "name", e.target.value)}
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                placeholder="Item name"
              />
              <select
                value={item.category || "Other"}
                onChange={(e) => updateItem(index, "category", e.target.value)}
                className="px-2 py-2 border border-gray-200 rounded-lg text-xs text-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none bg-white"
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
              {item.productId && (
                <span className="text-xs text-gray-400 font-mono px-2">
                  #{item.productId}
                </span>
              )}
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                  $
                </span>
                <input
                  type="number"
                  step="0.01"
                  value={item.price}
                  onChange={(e) =>
                    updateItem(index, "price", parseFloat(e.target.value) || 0)
                  }
                  className="w-24 pl-7 pr-3 py-2 border border-gray-200 rounded-lg text-sm text-right focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>
              <button
                onClick={() => removeItem(index)}
                className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-opacity p-1"
                title="Remove item"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <button
          onClick={addItem}
          className="mt-3 text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          + Add item
        </button>
      </div>

      {/* Subtotal, Tax, Tip, Total */}
      <div className="border-t border-gray-200 px-6 py-4 space-y-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-500">Subtotal</span>
          <span className="text-sm text-gray-700 font-medium w-28 text-right">
            ${subtotal.toFixed(2)}
          </span>
        </div>
        {[
          { label: "Tax", value: tax, setter: setTax },
          { label: "Tip", value: tip, setter: setTip },
        ].map(({ label, value, setter }) => (
          <div key={label} className="flex justify-between items-center">
            <span className="text-sm text-gray-500">{label}</span>
            <div className="relative inline-block">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                $
              </span>
              <input
                type="number"
                step="0.01"
                value={value}
                onChange={(e) => setter(e.target.value)}
                className="w-28 pl-7 pr-3 py-1.5 border border-gray-200 rounded-lg text-sm text-right focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                placeholder="0.00"
              />
            </div>
          </div>
        ))}
        <div className="flex justify-between items-center pt-2 border-t border-gray-100">
          <span className="font-semibold text-gray-700">Total</span>
          <span className="font-bold text-lg text-gray-900 w-28 text-right">
            ${total.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Raw text toggle */}
      {receipt.rawText && (
        <div className="border-t border-gray-100 px-6 py-3">
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {showRaw ? "Hide" : "Show"} raw OCR text
          </button>
          {showRaw && (
            <pre className="mt-2 text-xs text-gray-500 bg-gray-50 p-3 rounded overflow-x-auto whitespace-pre-wrap max-h-48">
              {receipt.rawText}
            </pre>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="border-t border-gray-200 px-6 py-4 flex gap-3 justify-end bg-gray-50">
        <button
          onClick={onDiscard}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
        >
          Discard
        </button>
        <button
          onClick={handleSave}
          className="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors font-medium"
        >
          {receipt.id != null ? "Update" : "Save to History"}
        </button>
      </div>
    </div>
  );
}
