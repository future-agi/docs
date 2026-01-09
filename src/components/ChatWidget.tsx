/**
 * AI Chat Widget for Docs Site
 * React component that wraps @futureagi/chat-widget
 */
import { ChatSidebar } from '@futureagi/chat-widget';
import '@futureagi/chat-widget/styles.css';

// API URL - use relative path for same-origin or full URL for cross-origin
const API_URL = import.meta.env.PUBLIC_CHAT_API_URL || 'http://localhost:3002/api/v1/chat';

export default function ChatWidget() {
  return (
    <ChatSidebar
      config={{
        apiUrl: API_URL,
        title: 'AI Assistant',
        welcomeMessage: 'Ask me anything about FutureAGI, evaluations, tracing, or our SDK.',
        quickQuestions: [
          'How do I evaluate an LLM?',
          'How do I set up tracing?',
          'What metrics are available?',
        ],
        placeholder: 'Ask a question...',
        theme: 'dark',
      }}
      defaultOpen={false}
      width={360}
    />
  );
}
