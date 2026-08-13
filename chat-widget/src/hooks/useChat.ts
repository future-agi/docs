import { useChatContext } from '../context/ChatProvider.js';

/**
 * Hook to access chat functionality
 * Must be used within a ChatProvider
 */
export function useChat() {
  const context = useChatContext();

  return {
    // State
    messages: context.messages,
    isLoading: context.isLoading,
    isOpen: context.isOpen,
    error: context.error,
    suggestions: context.suggestions,

    // Actions
    sendMessage: context.sendMessage,
    clearMessages: context.clearMessages,
    openChat: context.openChat,
    closeChat: context.closeChat,
    toggleChat: context.toggleChat,

    // Config
    config: context.config,
  };
}

export default useChat;
