import { useRef, useState, useCallback } from "react";

export default function UploadArea({ onUpload, loading }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    (file) => {
      if (file && file.type.startsWith("image/")) {
        onUpload(file);
      }
    },
    [onUpload]
  );

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  function handleChange(e) {
    handleFile(e.target.files[0]);
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => inputRef.current?.click()}
      className={`
        bg-white rounded-lg shadow border-2 border-dashed p-12 text-center cursor-pointer
        transition-colors duration-200
        ${dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"}
        ${loading ? "pointer-events-none opacity-50" : ""}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleChange}
        className="hidden"
      />
      <div className="text-4xl mb-3">📷</div>
      <p className="text-lg font-medium text-gray-700">
        {dragOver ? "Drop your receipt here" : "Upload a receipt"}
      </p>
      <p className="text-sm text-gray-500 mt-1">
        Drag & drop, click to browse, or take a photo on mobile
      </p>
    </div>
  );
}
