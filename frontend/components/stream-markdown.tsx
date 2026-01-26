"use client";

import { Streamdown } from "streamdown";
import type { BundledTheme } from "streamdown";
import { useMemo } from "react";

interface StreamMarkdownProps {
    content: string;
    isStreaming?: boolean;
    className?: string;
    onCitationClick?: () => void;
}

/**
 * Markdown renderer optimized for AI streaming responses.
 * 
 * Uses Vercel's streamdown library which handles:
 * - Incomplete markdown during streaming (unclosed tags, etc.)
 * - Syntax highlighting for code blocks
 * - GFM support (tables, task lists, strikethrough)
 * - Security hardening for untrusted content
 * 
 * Also converts [Source N] citations to styled superscript elements.
 */
export function StreamMarkdown({
    content,
    isStreaming = false,
    className = "",
    onCitationClick
}: StreamMarkdownProps) {
    const shikiTheme: [BundledTheme, BundledTheme] = ["github-dark", "github-light"];

    // Preprocess content to convert [Source N] to markdown superscript
    // This converts [Source 1] to <sup>[1]</sup> style rendering
    const processedContent = useMemo(() => {
        if (!content) return content;

        // Replace [Source N] or [Source N, M, ...] patterns with superscript markdown
        // We'll use HTML since streamdown supports it
        return content.replace(
            /\[Source\s*(\d+(?:\s*,\s*\d+)*)\]/gi,
            (_, nums: string) => {
                const numbers = nums.split(',').map((n: string) => n.trim()).join(',');
                return `<sup class="citation">[${numbers}]</sup>`;
            }
        );
    }, [content]);

    return (
        <div className={`streamdown-content prose prose-slate prose-sm max-w-none ${className}`}>
            <style jsx global>{`
                .streamdown-content sup.citation {
                    color: rgb(5 150 105);
                    font-weight: 500;
                    cursor: pointer;
                    transition: color 0.15s;
                    margin-left: 1px;
                }
                .streamdown-content sup.citation:hover {
                    color: rgb(4 120 87);
                }
            `}</style>
            <Streamdown
                mode={isStreaming ? "streaming" : "static"}
                parseIncompleteMarkdown={isStreaming}
                className="leading-relaxed text-slate-700"
                shikiTheme={shikiTheme}
            >
                {processedContent}
            </Streamdown>
            {isStreaming && (
                <span className="inline-block w-2 h-5 bg-emerald-500 animate-pulse ml-0.5 rounded-sm" />
            )}
        </div>
    );
}
