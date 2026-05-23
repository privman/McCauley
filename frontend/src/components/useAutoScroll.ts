import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

const BOTTOM_THRESHOLD_PX = 24;

/**
 * Keep a scroll container pinned to the bottom while content grows, but
 * only if the user was already at (or near) the bottom. If they scrolled
 * up to read earlier content, leave their position alone.
 *
 * Pass any state that affects rendered content to `deps` so the hook
 * re-runs the bottom check after each change (e.g. messages, streaming
 * partial).
 *
 * Returns:
 *   - ref: attach to the scrollable element
 *   - stickToBottom: call to force-stick (e.g. when the user just sent a
 *     message and should see it + the response regardless of prior scroll)
 */
export function useAutoScroll<T extends HTMLElement>(
  deps: ReadonlyArray<unknown>,
) {
  const ref = useRef<T | null>(null);
  const shouldStickRef = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      const distanceFromBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight;
      shouldStickRef.current = distanceFromBottom <= BOTTOM_THRESHOLD_PX;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (shouldStickRef.current) {
      el.scrollTop = el.scrollHeight;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const stickToBottom = useCallback(() => {
    shouldStickRef.current = true;
  }, []);

  return { ref, stickToBottom };
}
