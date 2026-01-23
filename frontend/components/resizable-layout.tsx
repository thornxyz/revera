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
    defaultWidth,
    minWidth = 80,
    maxWidth = 500,
}: ResizableLayoutProps) {
    const [sidebarWidth, setSidebarWidth] = useState(defaultWidth ?? 280);
    const [isResizing, setIsResizing] = useState(false);
    const [hasCustomWidth, setHasCustomWidth] = useState(Boolean(defaultWidth));
    const [minWidthFloor, setMinWidthFloor] = useState(minWidth);
    const sidebarRef = useRef<HTMLDivElement>(null);

    const startResizing = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsResizing(true);
        setHasCustomWidth(true);
    }, []);

    const stopResizing = useCallback(() => {
        setIsResizing(false);
    }, []);

    const resize = useCallback(
        (e: MouseEvent) => {
            if (isResizing && sidebarRef.current) {
                const newWidth = e.clientX - sidebarRef.current.getBoundingClientRect().left;
                if (newWidth >= minWidthFloor && newWidth <= maxWidth) {
                    setSidebarWidth(newWidth);
                }
            }
        },
        [isResizing, minWidthFloor, maxWidth]
    );

    useEffect(() => {
        const updateSizing = () => {
            const viewportWidth = window.innerWidth;
            const nextMinWidth = Math.max(minWidth, Math.round(viewportWidth * 0.125));
            setMinWidthFloor(nextMinWidth);

            if (defaultWidth) {
                setSidebarWidth(Math.max(defaultWidth, nextMinWidth));
                return;
            }

            if (!hasCustomWidth) {
                const nextWidth = Math.max(
                    nextMinWidth,
                    Math.min(maxWidth, Math.round(viewportWidth * 0.25))
                );
                setSidebarWidth(nextWidth);
            } else {
                setSidebarWidth((prev) => Math.max(prev, nextMinWidth));
            }
        };

        updateSizing();
        window.addEventListener("resize", updateSizing);
        return () => window.removeEventListener("resize", updateSizing);
    }, [defaultWidth, minWidth, maxWidth, hasCustomWidth]);

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
                className="shrink-0 border-r border-slate-200/70 bg-white/80 backdrop-blur-sm overflow-x-auto overflow-y-hidden"
            >
                {sidebar}
            </div>

            {/* Resize Handle */}
            <div
                className={`w-1.5 cursor-col-resize shrink-0 transition-colors ${isResizing ? "bg-emerald-400" : "bg-slate-200/80 hover:bg-emerald-300/70"
                    }`}
                onMouseDown={startResizing}
            />

            {/* Main Content */}
            <div className="flex-1 min-w-0 overflow-hidden">
                {children}
            </div>
        </div>
    );
}
