import { useEffect, useRef } from 'react';

export default function GiscusComments({ pagePath }: { pagePath: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || ref.current.querySelector('.giscus')) return;

    const script = document.createElement('script');
    script.src = 'https://giscus.app/client.js';
    script.setAttribute('data-repo', 'future-agi/docs');
    script.setAttribute('data-repo-id', 'R_kgDONLxlGw');
    script.setAttribute('data-category', 'Docs');
    script.setAttribute('data-category-id', 'DIC_kwDONLxlG84C23G0');
    script.setAttribute('data-mapping', 'pathname');
    script.setAttribute('data-strict', '0');
    script.setAttribute('data-reactions-enabled', '1');
    script.setAttribute('data-emit-metadata', '0');
    script.setAttribute('data-input-position', 'top');
    script.setAttribute('data-theme', 'noborder_dark');
    script.setAttribute('data-lang', 'en');
    script.setAttribute('data-loading', 'lazy');
    script.crossOrigin = 'anonymous';
    script.async = true;

    ref.current.appendChild(script);
  }, [pagePath]);

  return (
    <div>
      <p className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">Questions & Discussion</p>
      <div ref={ref} />
    </div>
  );
}
