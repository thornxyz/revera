import { useState, useCallback } from 'react';

export function useUIState() {
    const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
    const [isReasoningExpanded, setIsReasoningExpanded] = useState(true);

    const toggleReasoningExpanded = useCallback(() => {
        setIsReasoningExpanded(prev => !prev);
    }, []);

    return {
        uploadDialogOpen,
        setUploadDialogOpen,
        activeTab,
        setActiveTab,
        isReasoningExpanded,
        setIsReasoningExpanded,
        toggleReasoningExpanded,
    };
}
