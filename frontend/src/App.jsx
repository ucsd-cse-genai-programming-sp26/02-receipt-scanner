import { useState, useEffect, useCallback } from "react";
import AuthForm from "./components/AuthForm";
import UploadArea from "./components/UploadArea";
import ReceiptCard from "./components/ReceiptCard";
import ReceiptHistory from "./components/ReceiptHistory";
import SpendingChart from "./components/SpendingChart";
import MonthlySummary from "./components/MonthlySummary";

const TOKEN_KEY = "receipt_scanner_token";
const USER_KEY = "receipt_scanner_user";

export default function App() {
  const [receipt, setReceipt] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [statsKey, setStatsKey] = useState(0);
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  });

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
    setReceipt(null);
    setHistory([]);
    setPreviewUrl(null);
  }, []);

  const apiFetch = useCallback(
    async (url, options = {}) => {
      const headers = { ...(options.headers || {}) };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const res = await fetch(url, { ...options, headers });
      if (res.status === 401) logout();
      return res;
    },
    [token, logout]
  );

  useEffect(() => {
    if (!token) return;
    fetchHistory();
  }, [token]);

  async function fetchHistory() {
    try {
      const res = await apiFetch("/api/receipts");
      if (res.ok) setHistory(await res.json());
    } catch {
      // silently fail on history load
    }
  }

  async function handleUpload(file) {
    setLoading(true);
    setError(null);
    setReceipt(null);
    setPreviewUrl(URL.createObjectURL(file));

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiFetch("/api/scan", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      data.scannedAt = new Date().toISOString();
      setReceipt(data);
    } catch (err) {
      setError(err.message || "Failed to scan receipt");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(updatedReceipt) {
    try {
      const isExisting = updatedReceipt.id != null;
      const url = isExisting
        ? `/api/receipts/${updatedReceipt.id}`
        : "/api/receipts";
      const method = isExisting ? "PUT" : "POST";
      const res = await apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedReceipt),
      });
      if (!res.ok) throw new Error("Failed to save receipt");
      await fetchHistory();
      setStatsKey((k) => k + 1);
    } catch (err) {
      setError(err.message);
    }
    setReceipt(null);
    setPreviewUrl(null);
  }

  function handleDiscard() {
    setReceipt(null);
    setPreviewUrl(null);
  }

  async function handleDeleteHistory(receiptId) {
    try {
      await apiFetch(`/api/receipts/${receiptId}`, { method: "DELETE" });
      await fetchHistory();
      setStatsKey((k) => k + 1);
    } catch {
      // silently fail
    }
  }

  function handleViewHistory(item) {
    setReceipt(item);
    setPreviewUrl(null);
  }

  function handleAuthenticated(accessToken, currentUser) {
    localStorage.setItem(TOKEN_KEY, accessToken);
    localStorage.setItem(USER_KEY, JSON.stringify(currentUser));
    setToken(accessToken);
    setUser(currentUser);
  }

  if (!token || !user) {
    return (
      <div className="min-h-screen bg-gray-50 px-4 py-8">
        <header className="max-w-3xl mx-auto text-center mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Receipt Scanner</h1>
          <p className="text-sm text-gray-500 mt-1">
            Securely scan receipts, categorize with AI, and track your monthly budget.
          </p>
        </header>
        <AuthForm onAuthenticated={handleAuthenticated} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              Receipt Scanner
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Signed in as {user.username}
            </p>
          </div>
          <button
            onClick={logout}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-100"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {!receipt && (
          <UploadArea onUpload={handleUpload} loading={loading} />
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            <p className="font-medium">Scan failed</p>
            <p className="text-sm">{error}</p>
          </div>
        )}

        {loading && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-gray-600">Scanning receipt...</p>
            {previewUrl && (
              <img
                src={previewUrl}
                alt="Receipt preview"
                className="mt-4 max-h-48 mx-auto rounded opacity-50"
              />
            )}
          </div>
        )}

        {receipt && !loading && (
          <ReceiptCard
            receipt={receipt}
            previewUrl={previewUrl}
            onSave={handleSave}
            onDiscard={handleDiscard}
          />
        )}

        {history.length > 0 && (
          <ReceiptHistory
            history={history}
            onDelete={handleDeleteHistory}
            onView={handleViewHistory}
          />
        )}

        <MonthlySummary apiFetch={apiFetch} refreshKey={statsKey} />
        <SpendingChart key={statsKey} apiFetch={apiFetch} />
      </main>
    </div>
  );
}
