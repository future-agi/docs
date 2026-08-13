import { ChatProvider, useChatContext } from '../context/ChatProvider.js';
import { ChatMessages } from './ChatMessages.js';
import { ChatInput } from './ChatInput.js';
import { ChatSuggestions } from './ChatSuggestions.js';
import type { ChatConfig } from '../types.js';

interface ChatEmbedProps {
  config: Partial<ChatConfig>;
  /** Height of the widget */
  height?: number | string;
  /** Whether to show the header */
  showHeader?: boolean;
  className?: string;
}

/**
 * Chat Embed Component
 * An inline chat widget that can be embedded anywhere
 */
export function ChatEmbed({
  config,
  height = 500,
  showHeader = true,
  className = '',
}: ChatEmbedProps) {
  return (
    <ChatProvider config={config} defaultOpen={true}>
      <ChatEmbedContent height={height} showHeader={showHeader} className={className} />
    </ChatProvider>
  );
}

function ChatEmbedContent({
  height,
  showHeader,
  className,
}: {
  height: number | string;
  showHeader: boolean;
  className: string;
}) {
  const {
    messages,
    isLoading,
    suggestions,
    sendMessage,
    clearMessages,
    config,
  } = useChatContext();

  const heightStyle = typeof height === 'number' ? `${height}px` : height;

  return (
    <div
      className={`fagi-embed ${className}`}
      style={{ height: heightStyle }}
    >
      {/* Header */}
      {showHeader && (
        <div className="fagi-embed-header">
          <div className="fagi-embed-title">
            <svg className="fagi-embed-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span>{config.title}</span>
          </div>
          {messages.length > 0 && (
            <button
              className="fagi-clear-btn"
              onClick={clearMessages}
              aria-label="Clear chat"
              title="Clear conversation"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3,6 5,6 21,6" />
                <path d="M19,6v14a2,2,0,0,1-2,2H7a2,2,0,0,1-2-2V6M8,6V4a2,2,0,0,1,2-2h4a2,2,0,0,1,2,2V6" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Messages */}
      <ChatMessages
        messages={messages}
        isLoading={isLoading}
        welcomeMessage={config.welcomeMessage}
        quickQuestions={config.quickQuestions}
        onQuickQuestion={sendMessage}
      />

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <ChatSuggestions
          suggestions={suggestions}
          onSelect={sendMessage}
        />
      )}

      {/* Input */}
      <ChatInput
        onSend={sendMessage}
        disabled={isLoading}
        placeholder={config.placeholder}
      />
    </div>
  );
}

export default ChatEmbed;
