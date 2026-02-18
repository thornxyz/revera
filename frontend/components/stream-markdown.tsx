"use client";

import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { useMemo } from "react";

// Import KaTeX styles for math rendering
import "katex/dist/katex.min.css";

interface StreamMarkdownProps {
    content: string;
    isStreaming?: boolean;
    className?: string;
    onCitationClick?: () => void;
}

/**
 * HAST node type passed by Streamdown via the `node` prop.
 */
interface HastNode {
    type?: string;
    tagName?: string;
    children?: HastNode[];
}

/**
 * Recursively checks if a HAST node tree contains an <img> element.
 * Streamdown wraps images in <div> wrappers, so if a <p> contains an
 * image the resulting HTML would be <p><div>...</div></p> which is invalid.
 */
function hastContainsImage(node: HastNode): boolean {
    if (node.tagName === "img") return true;
    return node.children?.some(hastContainsImage) ?? false;
}

/**
 * Custom paragraph component that avoids the <div> inside <p> hydration error.
 * Streamdown passes a HAST `node` prop to component overrides. We inspect it
 * to detect images and render a <div> instead of <p> when needed.
 */
function SafeParagraph({ node, ...rest }: React.HTMLAttributes<HTMLParagraphElement> & { node?: HastNode }) {
    if (node && hastContainsImage(node)) {
        return <div {...rest} />;
    }
    return <p {...rest} />;
}

/**
 * Markdown renderer optimized for AI streaming responses.
 * 
 * Uses Vercel's streamdown library which handles:
 * - Incomplete markdown during streaming (unclosed tags, etc.)
 * - Syntax highlighting for code blocks via @streamdown/code plugin
 * - LaTeX math rendering via @streamdown/math plugin (KaTeX)
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
                /* Code block styling */
                .streamdown-content pre {
                    border-radius: 0.5rem;
                    margin: 1rem 0;
                }
                .streamdown-content code {
                    font-size: 0.85em;
                }
                .streamdown-content pre code {
                    display: block;
                    overflow-x: auto;
                    padding: 1rem;
                }
                .streamdown-content :not(pre) > code {
                    background-color: rgb(241 245 249);
                    padding: 0.2em 0.4em;
                    border-radius: 0.25rem;
                    color: rgb(30 41 59);
                }
                /* Math styling */
                .streamdown-content .katex-display {
                    margin: 1rem 0;
                    overflow-x: auto;
                }
            `}</style>
            <Streamdown
                plugins={{
                    code: code,
                    math: math,
                }}
                components={{
                    p: SafeParagraph,
                }}
                isAnimating={isStreaming}
                className="leading-relaxed text-slate-700"
            >
                {processedContent}
            </Streamdown>
            {isStreaming && (
                <span className="inline-block w-2 h-5 bg-emerald-500 animate-pulse ml-0.5 rounded-sm" />
            )}
        </div>
    );
}
