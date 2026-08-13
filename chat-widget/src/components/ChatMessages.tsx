import { useEffect, useRef } from 'react';
import type { ChatMessage, Citation } from '../types.js';

interface ChatMessagesProps {
  messages: ChatMessage[];
  isLoading: boolean;
  error?: string | null;
  welcomeMessage?: string;
  quickQuestions?: string[];
  onQuickQuestion?: (question: string) => void;
  className?: string;
}

export function ChatMessages({
  messages,
  isLoading,
  error,
  welcomeMessage,
  quickQuestions = [],
  onQuickQuestion,
  className = '',
}: ChatMessagesProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  const showWelcome = messages.length === 0;

  return (
    <div ref={containerRef} className={`fagi-chat-messages ${className}`}>
      {showWelcome && (
        <div className="fagi-welcome">
          {welcomeMessage && <p className="fagi-welcome-text">{welcomeMessage}</p>}

          {quickQuestions.length > 0 && (
            <div className="fagi-quick-questions">
              {quickQuestions.map((question, index) => (
                <button
                  key={index}
                  className="fagi-quick-question"
                  onClick={() => onQuickQuestion?.(question)}
                  type="button"
                >
                  {question}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {/* Show typing indicator when loading and last message is user's or empty assistant */}
      {isLoading && (messages.length === 0 ||
        messages[messages.length - 1]?.role === 'user' ||
        (messages[messages.length - 1]?.role === 'assistant' && !messages[messages.length - 1]?.content)
      ) && (
        <div className="fagi-message fagi-message-assistant">
          <div className="fagi-message-content">
            <TypingIndicator />
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="fagi-error-banner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isStreaming = message.isStreaming;
  const isEmpty = !message.content || message.content.trim() === '';

  return (
    <div className={`fagi-message fagi-message-${message.role}`}>
      <div className="fagi-message-content">
        {isStreaming && isEmpty ? (
          <TypingIndicator />
        ) : (
          <>
            <MessageContent content={message.content} />
            {message.citations && message.citations.length > 0 && (
              <Citations citations={message.citations} />
            )}
            {isStreaming && <span className="fagi-streaming-cursor">|</span>}
          </>
        )}
      </div>
    </div>
  );
}

interface MessageContentProps {
  content: string;
}

function MessageContent({ content }: MessageContentProps) {
  if (!content) return null;

  // Parse the content into structured elements
  const elements: React.ReactNode[] = [];
  const lines = content.split('\n');
  let inCodeBlock = false;
  let codeBlockContent: string[] = [];
  let codeBlockLang = '';

  lines.forEach((line, lineIndex) => {
    // Handle code block start/end
    if (line.startsWith('```')) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeBlockLang = line.slice(3).trim();
        codeBlockContent = [];
      } else {
        inCodeBlock = false;
        elements.push(
          <pre key={`code-${lineIndex}`} className="fagi-md-pre">
            <code className={`fagi-md-code-block ${codeBlockLang ? `language-${codeBlockLang}` : ''}`}>
              {codeBlockContent.join('\n')}
            </code>
          </pre>
        );
        codeBlockContent = [];
        codeBlockLang = '';
      }
      return;
    }

    // Inside code block
    if (inCodeBlock) {
      codeBlockContent.push(line);
      return;
    }

    // Headers
    if (line.startsWith('### ')) {
      elements.push(<h5 key={lineIndex} className="fagi-md-h5">{line.slice(4)}</h5>);
      return;
    }
    if (line.startsWith('## ')) {
      elements.push(<h4 key={lineIndex} className="fagi-md-h4">{line.slice(3)}</h4>);
      return;
    }
    if (line.startsWith('# ')) {
      elements.push(<h3 key={lineIndex} className="fagi-md-h3">{line.slice(2)}</h3>);
      return;
    }

    // Horizontal rule
    if (line.match(/^---+$/) || line.match(/^\*\*\*+$/)) {
      elements.push(<hr key={lineIndex} className="fagi-md-hr" />);
      return;
    }

    // List items (unordered)
    if (line.match(/^[\s]*[-*]\s/)) {
      const indent = line.match(/^(\s*)/)?.[1].length || 0;
      const text = line.replace(/^[\s]*[-*]\s/, '');
      elements.push(
        <li key={lineIndex} className="fagi-md-li" style={{ marginLeft: `${Math.min(indent, 4) * 8}px` }}>
          <InlineFormatted text={text} />
        </li>
      );
      return;
    }

    // Numbered list
    if (line.match(/^[\s]*\d+\.\s/)) {
      const indent = line.match(/^(\s*)/)?.[1].length || 0;
      const text = line.replace(/^[\s]*\d+\.\s/, '');
      elements.push(
        <li key={lineIndex} className="fagi-md-li fagi-md-li-numbered" style={{ marginLeft: `${Math.min(indent, 4) * 8}px` }}>
          <InlineFormatted text={text} />
        </li>
      );
      return;
    }

    // Empty lines
    if (!line.trim()) {
      elements.push(<div key={lineIndex} className="fagi-md-spacer" />);
      return;
    }

    // Regular paragraph with inline formatting
    elements.push(
      <p key={lineIndex} className="fagi-md-p">
        <InlineFormatted text={line} />
      </p>
    );
  });

  // Handle unclosed code block
  if (inCodeBlock && codeBlockContent.length > 0) {
    elements.push(
      <pre key="code-unclosed" className="fagi-md-pre">
        <code className={`fagi-md-code-block ${codeBlockLang ? `language-${codeBlockLang}` : ''}`}>
          {codeBlockContent.join('\n')}
        </code>
      </pre>
    );
  }

  return <div className="fagi-message-text">{elements}</div>;
}

function InlineFormatted({ text }: { text: string }) {
  // Parse inline formatting: **bold**, *italic*, `code`, [link](url)
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let keyIndex = 0;

  while (remaining.length > 0) {
    // Try to match patterns
    const patterns = [
      // Links [text](url)
      { regex: /^\[([^\]]+)\]\(([^)]+)\)/, render: (match: RegExpMatchArray) => (
        <a key={keyIndex++} href={match[2]} target="_blank" rel="noopener noreferrer" className="fagi-md-link">
          {match[1]}
        </a>
      )},
      // Bold **text**
      { regex: /^\*\*([^*]+)\*\*/, render: (match: RegExpMatchArray) => (
        <strong key={keyIndex++}>{match[1]}</strong>
      )},
      // Italic *text*
      { regex: /^\*([^*]+)\*/, render: (match: RegExpMatchArray) => (
        <em key={keyIndex++}>{match[1]}</em>
      )},
      // Inline code `code`
      { regex: /^`([^`]+)`/, render: (match: RegExpMatchArray) => (
        <code key={keyIndex++} className="fagi-md-code">{match[1]}</code>
      )},
    ];

    let matched = false;
    for (const { regex, render } of patterns) {
      const match = remaining.match(regex);
      if (match) {
        parts.push(render(match));
        remaining = remaining.slice(match[0].length);
        matched = true;
        break;
      }
    }

    if (!matched) {
      // No pattern matched, consume one character
      const nextSpecial = remaining.slice(1).search(/[\[*`]/);
      if (nextSpecial === -1) {
        parts.push(<span key={keyIndex++}>{remaining}</span>);
        remaining = '';
      } else {
        parts.push(<span key={keyIndex++}>{remaining.slice(0, nextSpecial + 1)}</span>);
        remaining = remaining.slice(nextSpecial + 1);
      }
    }
  }

  return <>{parts}</>;
}

interface CitationsProps {
  citations: Citation[];
}

function Citations({ citations }: CitationsProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="fagi-citations">
      <div className="fagi-citations-header">Sources</div>
      <div className="fagi-citations-list">
        {citations.slice(0, 5).map((citation, index) => (
          <a
            key={index}
            href={citation.url || `/${citation.path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="fagi-citation"
          >
            <span className="fagi-citation-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14,2 14,8 20,8" />
              </svg>
            </span>
            <span className="fagi-citation-title">{citation.title}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="fagi-typing">
      <span></span>
      <span></span>
      <span></span>
    </div>
  );
}

export default ChatMessages;
