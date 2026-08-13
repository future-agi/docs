import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { ChatConfig, ChatContextValue, ChatMessage, ChatState, StreamEvent, ChatResponse } from '../types.js';

// Turnstile global type
declare global {
  interface Window {
    turnstile?: {
      render: (container: string | HTMLElement, options: {
        sitekey: string;
        callback: (token: string) => void;
        'error-callback'?: () => void;
        size?: 'invisible' | 'normal' | 'compact';
        appearance?: 'always' | 'execute' | 'interaction-only';
      }) => string;
      remove: (widgetId: string) => void;
    };
  }
}

let turnstileLoaded = false;
function loadTurnstileScript(): Promise<void> {
  if (turnstileLoaded || window.turnstile) {
    turnstileLoaded = true;
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.onload = () => { turnstileLoaded = true; resolve(); };
    script.onerror = () => reject(new Error('Failed to load Turnstile'));
    document.head.appendChild(script);
  });
}

function solveTurnstile(siteKey: string, mode: 'invisible' | 'visible'): Promise<string> {
  return new Promise(async (resolve, reject) => {
    try {
      await loadTurnstileScript();
    } catch {
      return reject(new Error('Failed to load Turnstile script'));
    }
    if (!window.turnstile) return reject(new Error('Turnstile not available'));

    // Create a hidden container for the widget
    let container = document.getElementById('turnstile-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'turnstile-container';
      container.style.position = 'fixed';
      container.style.bottom = '0';
      container.style.right = '0';
      container.style.zIndex = '99999';
      document.body.appendChild(container);
    }
    container.innerHTML = '';

    const widgetId = window.turnstile.render(container, {
      sitekey: siteKey,
      size: mode === 'invisible' ? 'invisible' : 'normal',
      appearance: mode === 'invisible' ? 'execute' : 'always',
      callback: (token: string) => {
        window.turnstile?.remove(widgetId);
        container!.innerHTML = '';
        resolve(token);
      },
      'error-callback': () => {
        window.turnstile?.remove(widgetId);
        container!.innerHTML = '';
        reject(new Error('Turnstile challenge failed'));
      },
    });
  });
}

const defaultConfig: ChatConfig = {
  apiUrl: '/api/v1/chat',
  streaming: true,
  welcomeMessage: 'Ask me anything about the documentation.',
  quickQuestions: [],
  placeholder: 'Ask a question...',
  title: 'AI Assistant',
  theme: 'dark',
  position: 'bottom-right',
};

const ChatContext = createContext<ChatContextValue | null>(null);

export function useChatContext(): ChatContextValue {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
}

interface ChatProviderProps {
  config: Partial<ChatConfig>;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export function ChatProvider({ config: userConfig, children, defaultOpen = false }: ChatProviderProps) {
  const config: ChatConfig = { ...defaultConfig, ...userConfig };

  const [state, setState] = useState<ChatState>({
    messages: [],
    isLoading: false,
    isOpen: defaultOpen,
    error: null,
    suggestions: [],
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  // Keep ref in sync with state for use in callbacks
  useEffect(() => {
    messagesRef.current = state.messages;
  }, [state.messages]);

  // Generate unique ID for messages
  const generateId = () => `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

  // Send message to API
  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || state.isLoading) return;

    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    // Add user message
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: message.trim(),
      timestamp: new Date(),
    };

    // Create placeholder for assistant response
    const assistantId = generateId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };

    // Build conversation history from CURRENT messages (not stale state)
    // Only include messages with actual content
    const conversationHistory = messagesRef.current
      .filter(m => m.content && m.content.trim().length > 0)
      .map(m => ({
        role: m.role,
        content: m.content,
      }));

    // Update state with both messages
    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage, assistantMessage],
      isLoading: true,
      error: null,
      suggestions: [],
    }));

    config.onMessageSent?.(message);

    try {
      const requestBody = {
        query: message.trim(),
        conversationHistory,
        stream: config.streaming !== false,
        includeMetadata: true,
        includeSuggestions: true,
      };

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'Accept': config.streaming !== false ? 'text/event-stream' : 'application/json',
      };

      if (config.apiKey) {
        headers['X-API-Key'] = config.apiKey;
      }

      let response = await fetch(config.apiUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
        signal: abortControllerRef.current.signal,
      });

      // Handle Turnstile challenge
      if (response.status === 403 && config.turnstileSiteKey) {
        try {
          const errorBody = await response.json() as { error?: { code?: string; challengeType?: string } };
          if (errorBody.error?.code === 'CHALLENGE_REQUIRED') {
            const mode = (errorBody.error.challengeType === 'visible' ? 'visible' : 'invisible') as 'visible' | 'invisible';
            const token = await solveTurnstile(config.turnstileSiteKey, mode);
            // Retry with token
            response = await fetch(config.apiUrl, {
              method: 'POST',
              headers,
              body: JSON.stringify({ ...requestBody, turnstileToken: token }),
              signal: abortControllerRef.current.signal,
            });
          }
        } catch (challengeErr) {
          throw new Error('Security verification failed. Please try again.');
        }
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API error: ${response.status} - ${errorText}`);
      }

      const contentType = response.headers.get('content-type') || '';

      if (config.streaming !== false && contentType.includes('text/event-stream')) {
        // Handle SSE streaming
        await handleStreamingResponse(response, assistantId);
      } else {
        // Handle regular JSON response
        const result = await response.json();
        const data: ChatResponse = result.data || result;

        updateAssistantMessage(assistantId, data.answer || 'No response received.', data.citations, false);

        if (data.suggestedQuestions && data.suggestedQuestions.length > 0) {
          setState(prev => ({
            ...prev,
            suggestions: data.suggestedQuestions!.map(q => ({ question: q })),
            isLoading: false,
          }));
        } else {
          setState(prev => ({ ...prev, isLoading: false }));
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return; // Request was cancelled
      }

      console.error('Chat error:', error);
      const errorMessage = error instanceof Error ? error.message : 'An error occurred';

      setState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
        messages: prev.messages.map(m =>
          m.id === assistantId
            ? { ...m, content: `Sorry, I encountered an error: ${errorMessage}`, isStreaming: false }
            : m
        ),
      }));
    }
  }, [state.isLoading, config]);

  // Handle SSE streaming response
  const handleStreamingResponse = async (response: Response, messageId: string) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEventType = 'message';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();

          // Empty line indicates end of an event
          if (!trimmedLine) {
            continue;
          }

          // Parse event type
          if (trimmedLine.startsWith('event:')) {
            currentEventType = trimmedLine.slice(6).trim();
            continue;
          }

          // Parse data
          if (trimmedLine.startsWith('data:')) {
            const data = trimmedLine.slice(5).trim();
            if (data) {
              try {
                const parsedData = JSON.parse(data);
                const event: StreamEvent = {
                  type: currentEventType as StreamEvent['type'],
                  data: parsedData,
                };
                handleStreamEvent(event, messageId);
              } catch (e) {
                console.warn('Failed to parse SSE data:', data, e);
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    setState(prev => ({ ...prev, isLoading: false }));
  };

  // Handle individual stream events
  const handleStreamEvent = (event: StreamEvent, messageId: string) => {
    switch (event.type) {
      case 'status': {
        // Status updates (classifying, routing, processing)
        // Could update UI to show status, for now just continue loading
        break;
      }
      case 'token': {
        // Real-time token streaming - update message with accumulated text
        const data = event.data as { text?: string; accumulated?: string };
        const content = data.accumulated || data.text || '';
        if (content) {
          updateAssistantMessage(messageId, content, undefined, true);
        }
        break;
      }
      case 'partial': {
        // Partial content update - the API sends { answer: string }
        const data = event.data as { answer?: string; content?: string };
        const content = data.answer || data.content || '';
        if (content) {
          updateAssistantMessage(messageId, content, undefined, true);
        }
        break;
      }
      case 'complete': {
        // Final complete response
        const data = event.data as ChatResponse;
        updateAssistantMessage(messageId, data.answer, data.citations, false);

        if (data.suggestedQuestions && data.suggestedQuestions.length > 0) {
          setState(prev => ({
            ...prev,
            suggestions: data.suggestedQuestions!.map(q => ({ question: q })),
          }));
        }

        config.onResponseReceived?.({
          id: messageId,
          role: 'assistant',
          content: data.answer,
          timestamp: new Date(),
          citations: data.citations,
        });
        break;
      }
      case 'suggestion': {
        // Individual suggestion from API
        const data = event.data as { question: string };
        if (data.question) {
          setState(prev => ({
            ...prev,
            suggestions: [...prev.suggestions, { question: data.question }],
          }));
        }
        break;
      }
      case 'suggestions': {
        // Batch suggestions
        const data = event.data as { questions: string[] };
        if (data.questions && data.questions.length > 0) {
          setState(prev => ({
            ...prev,
            suggestions: data.questions.map(q => ({ question: q })),
          }));
        }
        break;
      }
      case 'error': {
        const data = event.data as { message: string };
        setState(prev => ({
          ...prev,
          error: data.message,
          isLoading: false,
        }));
        updateAssistantMessage(messageId, `Error: ${data.message}`, undefined, false);
        break;
      }
      default: {
        // Unknown event type - log but don't crash
        console.warn('Unknown stream event type:', event.type);
      }
    }
  };

  // Update assistant message in state
  const updateAssistantMessage = (
    messageId: string,
    content: string,
    citations?: ChatMessage['citations'],
    isStreaming: boolean = false
  ) => {
    setState(prev => ({
      ...prev,
      isLoading: isStreaming,
      messages: prev.messages.map(m =>
        m.id === messageId
          ? { ...m, content, citations: citations || m.citations, isStreaming }
          : m
      ),
    }));
  };

  // Clear all messages
  const clearMessages = useCallback(() => {
    setState(prev => ({
      ...prev,
      messages: [],
      suggestions: [],
      error: null,
    }));
  }, []);

  // Open/close/toggle chat
  const openChat = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: true }));
    config.onOpen?.();
  }, [config]);

  const closeChat = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: false }));
    config.onClose?.();
  }, [config]);

  const toggleChat = useCallback(() => {
    setState(prev => {
      const newIsOpen = !prev.isOpen;
      if (newIsOpen) {
        config.onOpen?.();
      } else {
        config.onClose?.();
      }
      return { ...prev, isOpen: newIsOpen };
    });
  }, [config]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const value: ChatContextValue = {
    ...state,
    sendMessage,
    clearMessages,
    openChat,
    closeChat,
    toggleChat,
    config,
  };

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  );
}

export { ChatContext };
