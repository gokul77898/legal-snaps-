'use client';

import React, {
  ElementType,
  HTMLAttributes,
  useEffect,
  useRef,
  useState,
} from 'react';

type RevealProps = HTMLAttributes<HTMLElement> & {
  as?: ElementType;
  delay?: number;
  variant?: 'up' | 'soft';
};

/**
 * Reveals children once they enter the viewport. Falls back to visible when
 * IntersectionObserver is unavailable or the visitor prefers reduced motion.
 */
export const Reveal: React.FC<RevealProps> = ({
  as: Tag = 'div',
  delay = 0,
  variant = 'up',
  className = '',
  style,
  children,
  ...rest
}) => {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reduced || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin: '0px 0px -10% 0px', threshold: 0.06 },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const base = variant === 'soft' ? 'reveal-soft' : 'reveal';

  return (
    <Tag
      ref={ref}
      className={`${base} ${visible ? 'is-visible' : ''} ${className}`.trim()}
      style={{ ['--reveal-delay' as string]: `${delay}ms`, ...style }}
      {...rest}
    >
      {children}
    </Tag>
  );
};
