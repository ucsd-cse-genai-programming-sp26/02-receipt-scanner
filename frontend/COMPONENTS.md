# Receipt Scanner — Component Documentation

## Overview

The frontend is built with three React components that form a simple pipeline: **upload → view/edit → save**. They are orchestrated by `App.jsx`, which manages the shared state (current receipt, loading status, history) and passes callbacks down as props.

---

## 1. `UploadArea`

**File:** `src/components/UploadArea.jsx`

### Purpose

The entry point for the user. It provides a large, inviting drop zone where users can submit a receipt image. It supports three input methods to cover both desktop and mobile use cases.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `onUpload` | `(file: File) => void` | Called with the selected image file when the user provides one. |
| `loading` | `boolean` | When `true`, the component is visually dimmed and interaction is disabled to prevent duplicate submissions. |

### Input Methods

1. **Drag & Drop** — Users can drag an image file over the area and drop it. The border turns blue during hover to give visual feedback.
2. **Click to Browse** — Clicking anywhere on the area opens the native file picker (filtered to images via `accept="image/*"`).
3. **Mobile Camera Capture** — The hidden `<input>` includes `capture="environment"`, which prompts mobile browsers to open the rear camera directly.

### Key Behaviors

- Only files whose MIME type starts with `image/` are accepted; anything else is silently ignored.
- The file validation callback is wrapped in `useCallback` to avoid unnecessary re-renders in parent components.
- During loading, the component receives `pointer-events-none` and reduced opacity so the user can't trigger a second upload.

---

## 2. `ReceiptCard`

**File:** `src/components/ReceiptCard.jsx`

### Purpose

The core of the application. Once the backend returns parsed receipt data, this component renders it as an editable card. Every field — store name, date, individual item names/prices, and the total — is a live input that the user can correct if the OCR made mistakes.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `receipt` | `object` | The parsed receipt data from the backend. Expected shape: `{ storeName, date, items: [{ id, name, price, productId }], total, rawText, scannedAt }` |
| `previewUrl` | `string \| null` | A blob URL for the uploaded image, shown as a small thumbnail in the header. `null` when viewing from history. |
| `onSave` | `(updatedReceipt: object) => void` | Called with the edited receipt data when the user clicks "Save to History". |
| `onDiscard` | `() => void` | Called when the user clicks "Discard" to throw away the current scan. |

### Sections (top to bottom)

1. **Header (blue gradient)** — Editable store name and date inputs. If a preview image is available, it's shown as a small thumbnail on the right.
2. **Items list** — Each item is a row with an editable name input, an optional product ID badge (displayed if the OCR detected one), a dollar-amount input, and a remove button (✕) that appears on hover.
3. **Add item button** — Appends a blank item row so users can manually add items the OCR missed.
4. **Total section** — An editable total field. If the sum of the individual item prices doesn't match the entered total (off by more than $0.01), an amber warning shows the calculated sum so the user can investigate.
5. **Raw OCR text** — A collapsible section that shows the raw text Tesseract extracted. Useful for debugging or manually copying data the parser missed.
6. **Action buttons** — "Discard" (gray, outlined) and "Save to History" (blue, filled).

### Key Behaviors

- All receipt fields are copied into local `useState` hooks on mount, so edits don't mutate the original prop.
- `handleSave` merges the edited fields back into the original receipt object (preserving `rawText`, `scannedAt`, etc.) before calling `onSave`.
- The calculated-vs-entered total mismatch warning helps users catch OCR errors or missing items.

---

## 3. `ReceiptHistory`

**File:** `src/components/ReceiptHistory.jsx`

### Purpose

A simple list view of all previously saved receipts. It lives below the upload area on the main page and gives users quick access to past scans. Data is persisted in `localStorage` by the parent `App.jsx`.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `history` | `array` | Array of saved receipt objects (newest first). |
| `onDelete` | `(index: number) => void` | Called with the array index when the user clicks "Delete" on a receipt. |
| `onView` | `(receipt: object) => void` | Called with the receipt object when the user clicks a row, re-opening it in the `ReceiptCard` for viewing or further editing. |

### Display

Each row shows:
- **Store name** (bold) — falls back to "Unknown Store" if empty.
- **Summary line** — item count, total (if available), and date (if available), separated by `·` dots.
- **Delete button** — red text on the right side of each row.

### Key Behaviors

- Clicking the row text re-opens the receipt in the `ReceiptCard` editor (via `onView`), so users can review or re-edit past scans.
- The list is only rendered when `history.length > 0` (controlled by the parent `App.jsx`).
- Rows have a subtle hover background transition for visual polish.

---

## Data Flow

```
User uploads image
        │
        ▼
  UploadArea ──onUpload──▶ App.jsx ──POST /api/scan──▶ FastAPI backend
                                │
                                ▼
                          ReceiptCard (editable)
                           │            │
                      onSave        onDiscard
                           │            │
                           ▼            ▼
                   App.jsx adds     App.jsx clears
                   to history[]     current receipt
                           │
                           ▼
                    ReceiptHistory
                     │          │
                 onView      onDelete
                     │          │
                     ▼          ▼
               Re-opens in   Removes from
               ReceiptCard   history[]
```

All history state is saved to `localStorage` under the key `receipt-scanner-history` whenever it changes.
