/**
 * Checks if the current position in a markdown string is likely inside a block
 * that should not be split (like a triple-backtick code block or math block).
 */
export function isInsideSensitiveBlock(content: string, position: number): boolean {
    const textBefore = content.substring(0, position);

    // Check for code blocks (count backticks)
    const codeBlockMatches = textBefore.match(/```/g);
    const isInsideCode = codeBlockMatches ? codeBlockMatches.length % 2 !== 0 : false;

    if (isInsideCode) return true;

    // Check for math blocks (count double dollar signs)
    const mathBlockMatches = textBefore.match(/\$\$/g);
    const isInsideMath = mathBlockMatches ? mathBlockMatches.length % 2 !== 0 : false;

    return isInsideMath;
}

/**
 * Splits markdown content into "Stable" and "Active" parts for performance optimization.
 * Stable parts are finalized paragraphs that can be memoized.
 * Active part is the trailing portion currently being streamed.
 */
export function splitMarkdown(content: string, minStableLength: number = 3000): { stable: string; active: string } {
    if (content.length < minStableLength) {
        return { stable: "", active: content };
    }

    // Attempt to find a safe split point near the middle/end
    // We look for double newlines which signify paragraph boundaries
    const searchThreshold = content.length - 1000; // Keep at least 1000 chars in active part
    let splitIndex = -1;

    // Iterate backwards from threshold to find the last safe double newline
    const doubleNewline = "\n\n";
    let lastFound = content.lastIndexOf(doubleNewline, searchThreshold);

    while (lastFound !== -1) {
        if (!isInsideSensitiveBlock(content, lastFound)) {
            splitIndex = lastFound + doubleNewline.length;
            break;
        }
        lastFound = content.lastIndexOf(doubleNewline, lastFound - 1);
    }

    if (splitIndex === -1) {
        return { stable: "", active: content };
    }

    return {
        stable: content.substring(0, splitIndex),
        active: content.substring(splitIndex)
    };
}
