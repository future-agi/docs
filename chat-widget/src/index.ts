/**
 * @futureagi/chat-widget
 *
 * Embeddable AI chat widget for documentation sites
 *
 * Components:
 * - ChatSidebar: Slide-out panel from the right
 * - ChatBubble: Floating button with popup chat
 * - ChatEmbed: Inline embedded chat widget
 *
 * Usage:
 * ```tsx
 * import { ChatBubble } from '@futureagi/chat-widget';
 * import '@futureagi/chat-widget/styles.css';
 *
 * function App() {
 *   return (
 *     <ChatBubble
 *       config={{
 *         apiUrl: '/api/v1/chat',
 *         title: 'AI Assistant',
 *         welcomeMessage: 'Ask me anything!',
 *         quickQuestions: [
 *           'How do I get started?',
 *           'What features are available?',
 *         ],
 *       }}
 *     />
 *   );
 * }
 * ```
 */

// Components
export { ChatSidebar } from './components/ChatSidebar.js';
export { ChatBubble } from './components/ChatBubble.js';
export { ChatEmbed } from './components/ChatEmbed.js';
export { ChatMessages } from './components/ChatMessages.js';
export { ChatInput } from './components/ChatInput.js';
export { ChatSuggestions } from './components/ChatSuggestions.js';

// Context & Hooks
export { ChatProvider, useChatContext } from './context/ChatProvider.js';
export { useChat } from './hooks/useChat.js';

// Types
export type {
  ChatConfig,
  ChatMessage,
  ChatState,
  ChatContextValue,
  Citation,
  Suggestion,
  StreamEvent,
  ChatResponse,
} from './types.js';
