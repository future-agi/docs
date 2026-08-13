/**
 * Chat Widget Type Definitions
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  citations?: Citation[];
  isStreaming?: boolean;
}

export interface Citation {
  title: string;
  path: string;
  url?: string;
  snippet?: string;
}

export interface Suggestion {
  question: string;
  category?: string;
}

export interface ChatConfig {
  /** API endpoint for chat requests */
  apiUrl: string;
  /** Optional API key for authentication */
  apiKey?: string;
  /** Cloudflare Turnstile site key for challenge verification */
  turnstileSiteKey?: string;
  /** Enable streaming responses (default: true) */
  streaming?: boolean;
  /** Welcome message to show initially */
  welcomeMessage?: string;
  /** Quick questions to show at start */
  quickQuestions?: string[];
  /** Placeholder text for input */
  placeholder?: string;
  /** Title shown in header */
  title?: string;
  /** Theme: 'light', 'dark', or 'system' */
  theme?: 'light' | 'dark' | 'system';
  /** Position for bubble component */
  position?: 'bottom-right' | 'bottom-left';
  /** Custom CSS class names */
  classNames?: {
    container?: string;
    header?: string;
    messages?: string;
    input?: string;
  };
  /** Callback when chat opens */
  onOpen?: () => void;
  /** Callback when chat closes */
  onClose?: () => void;
  /** Callback when message is sent */
  onMessageSent?: (message: string) => void;
  /** Callback when response is received */
  onResponseReceived?: (response: ChatMessage) => void;
}

export interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  isOpen: boolean;
  error: string | null;
  suggestions: Suggestion[];
}

export interface ChatContextValue extends ChatState {
  sendMessage: (message: string) => Promise<void>;
  clearMessages: () => void;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;
  config: ChatConfig;
}

export interface StreamEvent {
  type: 'status' | 'routing' | 'processing' | 'token' | 'partial' | 'suggestion' | 'suggestions' | 'complete' | 'error';
  data: unknown;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  confidence?: number;
  specialist?: string;
  suggestedQuestions?: string[];
}
