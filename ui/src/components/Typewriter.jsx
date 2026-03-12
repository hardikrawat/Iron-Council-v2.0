
import React, { useState, useEffect, useRef } from 'react';

const Typewriter = ({ text = "", speed = 30, isStreaming = false }) => {
    const [displayedText, setDisplayedText] = useState("");
    const indexRef = useRef(0);
    const timeoutRef = useRef(null);

    useEffect(() => {
        // If the incoming text length is greater than what we've processed,
        // or if it's a completely new string (length 0 or shorter than current index).
        if (text.length < indexRef.current) {
            // Text was hard-reset or replaced with shorter text
            setDisplayedText("");
            indexRef.current = 0;
        }

        const typeNextChar = () => {
            if (indexRef.current < text.length) {
                setDisplayedText(text.substring(0, indexRef.current + 1));
                indexRef.current += 1;
                
                // Speed adjustment: type faster if we are far behind the "actual" text length
                // This helps keep up with streaming chunks.
                const remaining = text.length - indexRef.current;
                const dynamicSpeed = remaining > 50 ? speed / 4 : (remaining > 20 ? speed / 2 : speed);
                
                timeoutRef.current = setTimeout(typeNextChar, dynamicSpeed);
            }
        };

        // Start typing if not already in progress or if more text arrived
        if (!timeoutRef.current && indexRef.current < text.length) {
            typeNextChar();
        }

        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
        };
    }, [text, speed]);

    // If streaming ended and we are still typing, we should eventually catch up.
    // However, if the user wants it to FEEL like streaming, this lag is fine.
    
    return <span>{displayedText}</span>;
};

export default Typewriter;
