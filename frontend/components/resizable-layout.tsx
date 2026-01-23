"use client";

import * as React from "react";
import { useState, useCallback, useRef, useEffect } from "react";

interface ResizableLayoutProps {
    sidebar: React.ReactNode;
    children: React.ReactNode;
    defaultWidth?: number;
    minWidth?: number;
    maxWidth?: number;
}

export function ResizableLayout({
    sidebar,
    children,
    defaultWidth = 320,
    minWidth = 200,
    maxWidth = 500,
}: ResizableLayoutProps) {
    const [sidebarWidth, setSidebarWidth] = useState(defaultWidth);
    const [isResizing, setIsResizing] = useState(false);
    const sidebarRef = useRef<HTMLDivElement>(null);

    const startResizing = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsResizing(true);
    }, []);

    const stopResizing = useCallback(() => {
        setIsResizing(false);
    }, []);

    const resize = useCallback(
        (e: MouseEvent) => {
            if (isResizing && sidebarRef.current) {
                const newWidth = e.clientX - sidebarRef.current.getBoundingClientRect().left;
                if (newWidth >= minWidth && newWidth <= maxWidth) {
                    setSidebarWidth(newWidth);
                }
            }
        },
        [isResizing, minWidth, maxWidth]
    );

    useEffect(() => {
        if (isResizing) {
            window.addEventListener("mousemove", resize);
            window.addEventListener("mouseup", stopResizing);
        }

        return () => {
            window.removeEventListener("mousemove", resize);
            window.removeEventListener("mouseup", stopResizing);
        };
    }, [isResizing, resize, stopResizing]);

    return (
        <div className="flex h-full w-full">
            {/* Sidebar */}
            <div
                ref={sidebarRef}
                style={{ width: sidebarWidth }}
                className="flex-shrink-0 border-r border-neutral-800/50 backdrop-blur-sm bg-neutral-900/30 overflow-hidden"
            >
                {sidebar}
            </div>

            {/* Resize Handle */}
            <div
                className={`w-1.5 cursor-col-resize flex-shrink-0 transition-colors ${isResizing ? "bg-violet-500" : "bg-neutral-800/50 hover:bg-violet-500/50"
                    }`}
                onMouseDown={startResizing}
            />

            {/* Main Content */}
            <div className="flex-1 overflow-hidden">
                {children}
            </div>
        </div>
    );
}
