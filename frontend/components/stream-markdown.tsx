import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { useMemo, memo } from "react";
import { splitMarkdown } from "@/lib/markdown-utils";

// Import KaTeX styles for math rendering
import "katex/dist/katex.min.css";

interface StreamMarkdownProps {
    content: string;
    isStreaming?: boolean;
    className?: string;
    onCitationClick?: () => void;
}

/**
 * A memoized block of finalized markdown.
 * Prevents expensive re-renders during the streaming of later content.
 */
const StableBlock = memo(function StableBlock({ content, className }: { content: string; className?: string }) {
    if (!content) return null;

    // Static markdown rendering for stable content
    return (
        <Streamdown
            plugins={{ code, math }}
            components={{ p: SafeParagraph }}
            isAnimating={false}
            className={className}
        >
            {content}
        </Streamdown>
    );
});

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
 */
function hastContainsImage(node: HastNode): boolean {
    if (node.tagName === "img") return true;
    return node.children?.some(hastContainsImage) ?? false;
}

/**
 * Custom paragraph component that avoids the <div> inside <p> hydration error.
 */
function SafeParagraph({ node, ...rest }: React.HTMLAttributes<HTMLParagraphElement> & { node?: HastNode }) {
    if (node && hastContainsImage(node)) {
        return <div {...rest} />;
    }
    return <p {...rest} />;
}

/**
 * StreamMarkdown component optimized for long streaming responses.
 * Uses a segmented rendering strategy to avoid UI lag.
 */
export function StreamMarkdown({
    content,
    isStreaming = false,
    className = "",
}: StreamMarkdownProps) {
    // 1. Process citations (global pre-processing)
    const processedContent = useMemo(() => {
        if (!content) return "";
        return content.replace(
            /\[Source\s*(\d+(?:\s*,\s*\d+)*)\]/gi,
            (_, nums: string) => {
                const numbers = nums.split(',').map((n: string) => n.trim()).join(',');
                return `<sup class="citation">[${numbers}]</sup>`;
            }
        );
    }, [content]);

    // 2. Segment content if it's long and streaming
    const { stable, active } = useMemo(() => {
        if (!isStreaming) return { stable: "", active: processedContent };
        return splitMarkdown(processedContent, 3000);
    }, [processedContent, isStreaming]);

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

            {/* Render the stable (finalized) part with heavy memoization */}
            {stable && <StableBlock content={stable} className="mb-0" />}

            {/* Render the active (currently streaming) tail */}
            {active && (
                <Streamdown
                    plugins={{ code, math }}
                    components={{ p: SafeParagraph }}
                    isAnimating={isStreaming}
                    className="leading-relaxed text-slate-700"
                >
                    {active}
                </Streamdown>
            )}

            {isStreaming && (
                <span className="inline-block w-1.5 h-4.5 bg-emerald-500 animate-pulse ml-0.5 rounded-sm align-middle" />
            )}
        </div>
    );
}
