import React, { useDeferredValue, useMemo, useRef, useState } from "react";

interface HighlightedSqlEditorProps {
  value: string;
  placeholder: string;
  onChange: (sql: string) => void;
  minHeightClassName?: string;
  suggestions?: SqlSuggestionItem[];
}

export interface SqlSuggestionItem {
  value: string;
  label?: string;
  detail?: string;
  kind?: "table" | "column" | "function";
}

const SQL_KEYWORDS = [
  "SELECT",
  "FROM",
  "WHERE",
  "GROUP BY",
  "ORDER BY",
  "LIMIT",
  "OFFSET",
  "JOIN",
  "INNER",
  "LEFT",
  "RIGHT",
  "FULL",
  "OUTER",
  "ON",
  "AS",
  "AND",
  "OR",
  "NOT",
  "IN",
  "IS",
  "NULL",
  "BETWEEN",
  "LIKE",
  "CASE",
  "WHEN",
  "THEN",
  "ELSE",
  "END",
  "DISTINCT",
  "COUNT",
  "SUM",
  "AVG",
  "MIN",
  "MAX",
  "WITH",
  "UNION",
  "ALL",
  "HAVING",
  "OVER",
  "PARTITION BY",
  "ROWS",
  "RANGE",
  "DESC",
  "ASC",
];

const TOKEN_PATTERN = new RegExp(
  [
    "--.*$",
    "/\\*[\\s\\S]*?\\*/",
    "'(?:''|[^'])*'",
    "\"(?:\"\"|[^\"])*\"",
    "\\{\\{[A-Z_]+\\}\\}",
    "\\b\\d+(?:\\.\\d+)?\\b",
    `\\b(?:${SQL_KEYWORDS.map((keyword) => keyword.replace(/\s+/g, "\\s+")).join("|")})\\b`,
  ].join("|"),
  "gim",
);

function getTokenClassName(token: string): string {
  if (token.startsWith("--") || token.startsWith("/*")) {
    return "text-slate-400";
  }
  if (token.startsWith("'") || token.startsWith("\"")) {
    return "text-emerald-700";
  }
  if (token.startsWith("{{") && token.endsWith("}}")) {
    return "rounded bg-amber-100 px-1 text-amber-800";
  }
  if (/^\d/.test(token)) {
    return "text-fuchsia-700";
  }
  return "font-semibold text-indigo-700";
}

function renderHighlightedSql(sql: string): React.ReactNode[] {
  const tokens: React.ReactNode[] = [];
  let lastIndex = 0;
  let matchIndex = 0;

  for (const match of sql.matchAll(TOKEN_PATTERN)) {
    const matchedText = match[0];
    const startIndex = match.index ?? 0;

    if (startIndex > lastIndex) {
      tokens.push(sql.slice(lastIndex, startIndex));
    }

    tokens.push(
      <span
        key={`${startIndex}-${matchIndex}`}
        data-token-type="sql-token"
        className={getTokenClassName(matchedText)}
      >
        {matchedText}
      </span>,
    );

    lastIndex = startIndex + matchedText.length;
    matchIndex += 1;
  }

  if (lastIndex < sql.length) {
    tokens.push(sql.slice(lastIndex));
  }

  return tokens;
}

const SQL_IDENTIFIER_TOKEN = /[A-Za-z0-9_."$]/;

function normalizeSuggestionText(value: string): string {
  return value.replace(/"/g, "").toLowerCase();
}

function getTokenBounds(sql: string, cursorIndex: number): { start: number; end: number; token: string } {
  let start = Math.max(0, cursorIndex);
  let end = Math.max(0, cursorIndex);

  while (start > 0 && SQL_IDENTIFIER_TOKEN.test(sql[start - 1])) {
    start -= 1;
  }

  while (end < sql.length && SQL_IDENTIFIER_TOKEN.test(sql[end])) {
    end += 1;
  }

  return {
    start,
    end,
    token: sql.slice(start, cursorIndex),
  };
}

function getFilteredSuggestions(
  token: string,
  suggestions: SqlSuggestionItem[],
): SqlSuggestionItem[] {
  const normalizedToken = normalizeSuggestionText(token).trim();
  if (!normalizedToken) {
    return [];
  }

  return suggestions
    .filter((suggestion) => {
      const values = [
        suggestion.value,
        suggestion.label || "",
        suggestion.detail || "",
      ].map(normalizeSuggestionText);

      return values.some((value) => value.includes(normalizedToken));
    })
    .sort((left, right) => {
      const leftValue = normalizeSuggestionText(left.value);
      const rightValue = normalizeSuggestionText(right.value);
      const leftSegment = leftValue.split(".").pop() || leftValue;
      const rightSegment = rightValue.split(".").pop() || rightValue;
      const leftRank = leftSegment.startsWith(normalizedToken) ? 0 : leftValue.startsWith(normalizedToken) ? 1 : 2;
      const rightRank = rightSegment.startsWith(normalizedToken) ? 0 : rightValue.startsWith(normalizedToken) ? 1 : 2;

      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }

      return leftValue.localeCompare(rightValue);
    })
    .slice(0, 8);
}

export const HighlightedSqlEditor: React.FC<HighlightedSqlEditorProps> = ({
  value,
  placeholder,
  onChange,
  minHeightClassName = "min-h-[260px]",
  suggestions = [],
}) => {
  const overlayRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const deferredSql = useDeferredValue(value);
  const highlightedSql = useMemo(() => renderHighlightedSql(deferredSql), [deferredSql]);
  const [cursorIndex, setCursorIndex] = useState(0);
  const [isFocused, setIsFocused] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);

  const suggestionContext = useMemo(() => {
    const bounds = getTokenBounds(value, cursorIndex);
    const items = getFilteredSuggestions(bounds.token, suggestions);

    return {
      ...bounds,
      items,
    };
  }, [cursorIndex, suggestions, value]);

  const hasSuggestions = isFocused && suggestionContext.items.length > 0;
  const activeSuggestion = hasSuggestions
    ? suggestionContext.items[Math.min(activeSuggestionIndex, suggestionContext.items.length - 1)]
    : null;

  const applySuggestion = (suggestion: SqlSuggestionItem) => {
    const nextValue =
      value.slice(0, suggestionContext.start) +
      suggestion.value +
      value.slice(suggestionContext.end);

    onChange(nextValue);

    window.requestAnimationFrame(() => {
      if (!textareaRef.current) return;
      const nextCursorIndex = suggestionContext.start + suggestion.value.length;
      textareaRef.current.focus();
      textareaRef.current.selectionStart = nextCursorIndex;
      textareaRef.current.selectionEnd = nextCursorIndex;
      setCursorIndex(nextCursorIndex);
      setActiveSuggestionIndex(0);
    });
  };

  const syncOverlayScroll = (event: React.UIEvent<HTMLTextAreaElement>) => {
    if (!overlayRef.current) return;
    overlayRef.current.scrollTop = event.currentTarget.scrollTop;
    overlayRef.current.scrollLeft = event.currentTarget.scrollLeft;
    setCursorIndex(event.currentTarget.selectionStart);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (hasSuggestions) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSuggestionIndex((currentIndex) =>
          currentIndex >= suggestionContext.items.length - 1 ? 0 : currentIndex + 1,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSuggestionIndex((currentIndex) =>
          currentIndex <= 0 ? suggestionContext.items.length - 1 : currentIndex - 1,
        );
        return;
      }

      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        if (activeSuggestion) {
          applySuggestion(activeSuggestion);
        }
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setActiveSuggestionIndex(0);
        return;
      }
    }

    if (event.key !== "Tab") return;

    event.preventDefault();
    const textarea = event.currentTarget;
    const selectionStart = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    const nextValue = `${value.slice(0, selectionStart)}  ${value.slice(selectionEnd)}`;

    onChange(nextValue);

    window.requestAnimationFrame(() => {
      textarea.selectionStart = selectionStart + 2;
      textarea.selectionEnd = selectionStart + 2;
    });
  };

  return (
    <div className="relative overflow-hidden rounded border border-gray-300 bg-slate-50 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-200">
      <div
        ref={overlayRef}
        aria-hidden="true"
        className={`pointer-events-none absolute inset-0 overflow-auto ${minHeightClassName}`}
      >
        <pre
          className={`m-0 min-w-full w-max p-3 font-mono text-sm leading-6 text-slate-700 ${minHeightClassName} whitespace-pre`}
        >
          {highlightedSql}
          {value.endsWith("\n") ? "\u200b" : null}
        </pre>
      </div>

      {!value && (
        <div className="pointer-events-none absolute left-3 top-3 text-sm text-slate-400">
          {placeholder}
        </div>
      )}

      <textarea
        ref={textareaRef}
        aria-label="SQL editor"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setCursorIndex(event.target.selectionStart);
          setActiveSuggestionIndex(0);
        }}
        onScroll={syncOverlayScroll}
        onKeyDown={handleKeyDown}
        onSelect={(event) => setCursorIndex(event.currentTarget.selectionStart)}
        onClick={(event) => setCursorIndex(event.currentTarget.selectionStart)}
        onKeyUp={(event) => setCursorIndex(event.currentTarget.selectionStart)}
        onFocus={(event) => {
          setIsFocused(true);
          setCursorIndex(event.currentTarget.selectionStart);
        }}
        onBlur={() => {
          window.setTimeout(() => {
            setIsFocused(false);
            setActiveSuggestionIndex(0);
          }, 0);
        }}
        wrap="off"
        className={`relative w-full resize-y overflow-auto whitespace-pre bg-transparent p-3 font-mono text-sm leading-6 text-transparent caret-slate-900 focus:outline-none ${minHeightClassName}`}
        spellCheck={false}
      />

      {hasSuggestions && (
        <div className="absolute bottom-3 left-3 right-3 z-10 max-h-56 overflow-y-auto rounded-md border border-slate-200 bg-white/95 shadow-lg backdrop-blur">
          {suggestionContext.items.map((suggestion) => (
            <button
              key={`${suggestion.kind || "suggestion"}:${suggestion.value}`}
              type="button"
              onMouseDown={(event) => {
                event.preventDefault();
                applySuggestion(suggestion);
              }}
              className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left text-sm ${
                suggestion === activeSuggestion ? "bg-indigo-50 text-indigo-900" : "text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className="min-w-0 flex-1 truncate font-mono">{suggestion.value}</span>
              <span className="shrink-0 text-[11px] uppercase tracking-wide text-slate-400">
                {suggestion.kind || "item"}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
