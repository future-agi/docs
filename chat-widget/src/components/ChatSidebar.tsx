import React, { useEffect } from 'react';
import { ChatProvider, useChatContext } from '../context/ChatProvider.js';
import { ChatMessages } from './ChatMessages.js';
import { ChatInput } from './ChatInput.js';
import { ChatSuggestions } from './ChatSuggestions.js';
import type { ChatConfig } from '../types.js';

interface ChatSidebarProps {
  config: Partial<ChatConfig>;
  defaultOpen?: boolean;
  width?: number | string;
}

/**
 * Chat Sidebar Component
 * A slide-out panel from the right side of the screen
 */
export function ChatSidebar({ config, defaultOpen = false, width = 360 }: ChatSidebarProps) {
  return (
    <ChatProvider config={config} defaultOpen={defaultOpen}>
      <ChatSidebarContent width={width} />
    </ChatProvider>
  );
}

function ChatSidebarContent({ width }: { width: number | string }) {
  const {
    messages,
    isLoading,
    isOpen,
    error,
    suggestions,
    sendMessage,
    clearMessages,
    openChat,
    closeChat,
    config,
  } = useChatContext();

  // Determine theme
  const theme = config.theme || 'dark';

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

  // Expose open/close functions globally for external triggering
  useEffect(() => {
    const toggle = () => isOpen ? closeChat() : openChat();

    // Set both fagi and legacy aiChat names for compatibility
    (window as any).openFagiChat = openChat;
    (window as any).closeFagiChat = closeChat;
    (window as any).toggleFagiChat = toggle;
    // Legacy names for backward compatibility
    (window as any).openAiChat = openChat;
    (window as any).closeAiChat = closeChat;
    (window as any).toggleAiChat = toggle;

    return () => {
      delete (window as any).openFagiChat;
      delete (window as any).closeFagiChat;
      delete (window as any).toggleFagiChat;
      delete (window as any).openAiChat;
      delete (window as any).closeAiChat;
      delete (window as any).toggleAiChat;
    };
  }, [openChat, closeChat, isOpen]);

  const widthStyle = typeof width === 'number' ? `${width}px` : width;

  return (
    <>
      {/* Backdrop for mobile */}
      {isOpen && (
        <div
          className="fagi-sidebar-backdrop"
          onClick={closeChat}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fagi-sidebar ${isOpen ? 'fagi-sidebar-open' : ''}`}
        style={{ '--fagi-sidebar-width': widthStyle } as React.CSSProperties}
        data-fagi-theme={theme}
        aria-hidden={!isOpen}
      >
        {/* Header */}
        <div className="fagi-sidebar-header">
          <div className="fagi-sidebar-title">
            <svg className="fagi-sidebar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
              title="Close (Esc)"
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

        {/* Footer */}
        <div className="fagi-sidebar-footer">
          Powered by AI
        </div>
      </aside>
    </>
  );
}

export default ChatSidebar;
