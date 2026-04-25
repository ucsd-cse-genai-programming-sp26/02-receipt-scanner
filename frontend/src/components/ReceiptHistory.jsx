export default function ReceiptHistory({ history, onDelete, onView }) {
  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">
          📋 Receipt History
        </h2>
      </div>
      <div className="divide-y divide-gray-100">
        {history.map((receipt) => (
          <div
            key={receipt.id}
            className="px-6 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <button
              onClick={() => onView(receipt)}
              className="flex-1 text-left"
            >
              <p className="font-medium text-gray-700">
                {receipt.storeName || "Unknown Store"}
              </p>
              <p className="text-sm text-gray-500">
                {receipt.items?.length || 0} items
                {receipt.total ? ` · $${parseFloat(receipt.total).toFixed(2)}` : ""}
                {receipt.date ? ` · ${receipt.date}` : ""}
              </p>
            </button>
            <button
              onClick={() => onDelete(receipt.id)}
              className="text-red-400 hover:text-red-600 text-sm ml-4"
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
