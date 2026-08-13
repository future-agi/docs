import type { Suggestion } from '../types.js';

interface ChatSuggestionsProps {
  suggestions: Suggestion[];
  onSelect: (question: string) => void;
  className?: string;
}

export function ChatSuggestions({
  suggestions,
  onSelect,
  className = '',
}: ChatSuggestionsProps) {
  if (suggestions.length === 0) return null;

  return (
    <div className={`fagi-suggestions ${className}`}>
      <div className="fagi-suggestions-header">Follow-up questions</div>
      <div className="fagi-suggestions-list">
        {suggestions.map((suggestion, index) => (
          <button
            key={index}
            className="fagi-suggestion"
            onClick={() => onSelect(suggestion.question)}
          >
            <span className="fagi-suggestion-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </span>
            <span className="fagi-suggestion-text">{suggestion.question}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default ChatSuggestions;
