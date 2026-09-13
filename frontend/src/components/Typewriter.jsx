import { useEffect, useState } from "react";

/**
 * Types out text character-by-character with a blinking cursor.
 * Calls onDone() when the full text is typed.
 */
export default function Typewriter({ text, speed = 28, onDone }) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed("");
    setDone(false);
    if (!text) {
      setDone(true);
      onDone?.();
      return;
    }
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setDone(true);
        onDone?.();
      }
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed, onDone]);

  return (
    <span className="typewriter-text">
      {displayed}
      {!done && <span className="typewriter-cursor">▋</span>}
    </span>
  );
}
