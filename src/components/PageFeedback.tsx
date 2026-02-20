import { useState, useEffect } from 'react';

export default function PageFeedback({ pagePath }: { pagePath: string }) {
  const storageKey = `docs-feedback:${pagePath}`;
  const [state, setState] = useState<'idle' | 'helpful' | 'not-helpful'>('idle');
  const [showTextarea, setShowTextarea] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved === 'helpful' || saved === 'not-helpful') {
      setState(saved);
    }
  }, [storageKey]);

  function trackEvent(name: string, props: Record<string, unknown>) {
    if (typeof window !== 'undefined' && (window as any).posthog?.capture) {
      (window as any).posthog.capture(name, props);
    }
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', name, props);
    }
    if (typeof window !== 'undefined' && (window as any).mixpanel?.track) {
      (window as any).mixpanel.track(name, props);
    }
    console.log(`[docs-feedback] ${name}`, props);
  }

  function handleVote(helpful: boolean) {
    const value = helpful ? 'helpful' : 'not-helpful';
    setState(value);
    localStorage.setItem(storageKey, value);
    setShowTextarea(true);
    trackEvent('docs_page_feedback', { page: pagePath, helpful });
  }

  function handleSubmitFeedback() {
    if (!feedback.trim()) return;
    trackEvent('docs_page_feedback_text', { page: pagePath, helpful: state === 'helpful', feedback: feedback.trim() });
    setSubmitted(true);
    setShowTextarea(false);
  }

  // After submitted
  if (state !== 'idle' && !showTextarea && submitted) {
    return (
      <div className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-secondary)] px-5 py-4 text-center">
        <div className="flex items-center justify-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <svg className="w-4 h-4 text-[var(--color-success)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Thanks for your feedback!
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-secondary)] px-5 py-4">
      <div className="flex flex-col items-center gap-3">
        <span className="text-sm text-[var(--color-text-secondary)]">Was this page helpful?</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleVote(true)}
            className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg border text-sm font-medium transition-all cursor-pointer ${
              state === 'helpful'
                ? 'border-[var(--color-success)] bg-[var(--color-success)]/10 text-[var(--color-success)]'
                : 'border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:border-[var(--color-success)] hover:text-[var(--color-success)] hover:bg-[var(--color-success)]/5'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14zm-9 11H3a2 2 0 01-2-2v-7a2 2 0 012-2h2" />
            </svg>
            Yes
          </button>
          <button
            onClick={() => handleVote(false)}
            className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg border text-sm font-medium transition-all cursor-pointer ${
              state === 'not-helpful'
                ? 'border-red-500 bg-red-500/10 text-red-400'
                : 'border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:border-red-500 hover:text-red-400 hover:bg-red-500/5'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10zm9-13h2a2 2 0 012 2v7a2 2 0 01-2 2h-2" />
            </svg>
            No
          </button>
        </div>
      </div>

      {showTextarea && (
        <div className="mt-4 space-y-2">
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder={state === 'helpful' ? 'What was most helpful?' : 'How can we improve this page?'}
            className="w-full px-3 py-2 text-sm bg-[var(--color-bg-tertiary)] border border-[var(--color-border-default)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-border-accent)] resize-none"
            rows={2}
          />
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => { setShowTextarea(false); setSubmitted(true); }}
              className="px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
            >
              Skip
            </button>
            <button
              onClick={handleSubmitFeedback}
              className="px-4 py-1.5 text-sm font-medium rounded-lg bg-[var(--color-accent-primary)] text-white hover:opacity-90 transition-opacity cursor-pointer"
            >
              Submit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
