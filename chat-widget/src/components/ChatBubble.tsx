import React, { useEffect } from 'react';
import { ChatProvider, useChatContext } from '../context/ChatProvider.js';
import { ChatMessages } from './ChatMessages.js';
import { ChatInput } from './ChatInput.js';
import { ChatSuggestions } from './ChatSuggestions.js';
import type { ChatConfig } from '../types.js';

interface ChatBubbleProps {
  config: Partial<ChatConfig>;
  /** Button size in pixels */
  size?: number;
  /** Offset from edge in pixels */
  offset?: number;
}

/**
 * Chat Bubble Component
 * A floating button that opens a chat popup
 */
export function ChatBubble({ config, size = 56, offset = 20 }: ChatBubbleProps) {
  const mergedConfig: Partial<ChatConfig> = {
    position: 'bottom-right',
    theme: 'dark',
    ...config,
  };

  return (
    <ChatProvider config={mergedConfig}>
      <ChatBubbleContent size={size} offset={offset} />
    </ChatProvider>
  );
}

function ChatBubbleContent({ size, offset }: { size: number; offset: number }) {
  const {
    messages,
    isLoading,
    isOpen,
    error,
    suggestions,
    sendMessage,
    clearMessages,
    toggleChat,
    closeChat,
    config,
  } = useChatContext();

  const position = config.position || 'bottom-right';
  const theme = config.theme || 'dark';
  const isRight = position.includes('right');
  const isBottom = position.includes('bottom');

  // ESC key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        closeChat();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeChat]);

  const positionStyles: React.CSSProperties = {
    [isRight ? 'right' : 'left']: `${offset}px`,
    [isBottom ? 'bottom' : 'top']: `${offset}px`,
  };

  const popupPositionStyles: React.CSSProperties = {
    [isRight ? 'right' : 'left']: `${offset}px`,
    [isBottom ? 'bottom' : 'top']: `${offset + size + 12}px`,
  };

  return (
    <>
      {/* Chat Popup */}
      <div
        className={`fagi-bubble-popup ${isOpen ? 'fagi-bubble-popup-open' : ''}`}
        style={popupPositionStyles}
        data-fagi-theme={theme}
        aria-hidden={!isOpen}
      >
        {/* Header */}
        <div className="fagi-bubble-header">
          <div className="fagi-bubble-title">
            <svg className="fagi-bubble-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span>{config.title}</span>
          </div>
          <div className="fagi-header-actions">
            {messages.length > 0 && (
              <button
                className="fagi-clear-btn"
                onClick={clearMessages}
                aria-label="Clear chat"
                title="Clear conversation"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                </svg>
              </button>
            )}
            <button
              className="fagi-close-btn"
              onClick={closeChat}
              aria-label="Close chat"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* Messages */}
        <ChatMessages
          messages={messages}
          isLoading={isLoading}
          error={error}
          welcomeMessage={config.welcomeMessage}
          quickQuestions={config.quickQuestions}
          onQuickQuestion={sendMessage}
        />

        {/* Suggestions */}
        {suggestions.length > 0 && !isLoading && (
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

      {/* Floating Button */}
      <button
        className={`fagi-bubble-btn ${isOpen ? 'fagi-bubble-btn-open' : ''}`}
        style={{
          ...positionStyles,
          width: `${size}px`,
          height: `${size}px`,
        }}
        onClick={toggleChat}
        aria-label={isOpen ? 'Close chat' : 'Open chat'}
        aria-expanded={isOpen}
      >
        <svg
          className="fagi-bubble-btn-icon fagi-bubble-btn-chat"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <svg
          className="fagi-bubble-btn-icon fagi-bubble-btn-close"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </>
  );
}

export default ChatBubble;
