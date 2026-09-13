import { useEffect, useState, useRef } from "react";

/**
 * Types out text character-by-character with a blinking cursor.
 * Calls onDone() when the full text is typed.
 */
export default function Typewriter({ text, speed = 35, onDone }) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);
  const onDoneRef = useRef(onDone);

  // Keep the latest onDone in a ref so it doesn't trigger the effect
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    setDisplayed("");
    setDone(false);
    if (!text) {
      setDone(true);
      onDoneRef.current?.();
      return;
    }
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setDone(true);
        onDoneRef.current?.();
      }
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed]);

  return (
    <span className="typewriter-text">
      {displayed}
      {!done && <span className="typewriter-cursor">▋</span>}
    </span>
  );
}
