import React, { useDeferredValue, useMemo, useState } from "react";

export interface SearchableSelectOption {
  value: string;
  label: string;
  description?: string;
}

interface SearchableSelectProps {
  value: string;
  options: SearchableSelectOption[];
  onChange: (value: string) => void;
  placeholder: string;
  searchPlaceholder?: string;
  disabled?: boolean;
  emptyMessage?: string;
  searchThreshold?: number;
  className?: string;
}

export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  value,
  options,
  onChange,
  placeholder,
  searchPlaceholder = "Search...",
  disabled = false,
  emptyMessage = "No options available.",
  searchThreshold = 20,
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const normalizedSearchTerm = deferredSearchTerm.trim().toLowerCase();
  const shouldShowSearch = options.length > searchThreshold;
  const selectedOption = options.find((option) => option.value === value);

  const visibleOptions = useMemo(() => {
    if (!shouldShowSearch || !normalizedSearchTerm) {
      return options;
    }

    return options.filter((option) => {
      const haystack = `${option.label} ${option.description ?? ""}`.toLowerCase();
      return haystack.includes(normalizedSearchTerm);
    });
  }, [normalizedSearchTerm, options, shouldShowSearch]);

  const handleSelect = (nextValue: string) => {
    onChange(nextValue);
    setIsOpen(false);
    setSearchTerm("");
  };

  return (
    <div className={`w-full ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        disabled={disabled}
        className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-left text-sm text-gray-900 transition hover:border-indigo-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
      >
        <span className="block truncate font-mono">{selectedOption?.label || placeholder}</span>
        {selectedOption?.description && (
          <span className="block truncate text-xs text-gray-400">{selectedOption.description}</span>
        )}
      </button>

      {isOpen && !disabled && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2 shadow-sm">
          {shouldShowSearch && (
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="mb-2 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder={searchPlaceholder}
            />
          )}

          <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
            {value && (
              <button
                type="button"
                onClick={() => handleSelect("")}
                className="w-full rounded px-2 py-2 text-left text-xs text-gray-500 transition hover:bg-white"
              >
                Clear selection
              </button>
            )}

            {visibleOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleSelect(option.value)}
                className={`w-full rounded px-2 py-2 text-left text-xs transition ${
                  option.value === value ? "bg-indigo-600 text-white" : "bg-white text-gray-800 hover:bg-indigo-50"
                }`}
              >
                <span className="block break-all font-mono">{option.label}</span>
                {option.description && (
                  <span className={option.value === value ? "text-indigo-100" : "text-gray-400"}>
                    {option.description}
                  </span>
                )}
              </button>
            ))}

            {visibleOptions.length === 0 && (
              <p className="px-2 py-4 text-center text-xs text-gray-400">{emptyMessage}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
