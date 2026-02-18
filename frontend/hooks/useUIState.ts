import { useState, useCallback } from 'react';

export function useUIState() {
    const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<"chat" | "attachments">("chat");
    const [attachmentsRefresh, setAttachmentsRefresh] = useState(0);
    const [isReasoningExpanded, setIsReasoningExpanded] = useState(true);

    const toggleReasoningExpanded = useCallback(() => {
        setIsReasoningExpanded(prev => !prev);
    }, []);

    const refreshAttachments = useCallback(() => {
        setAttachmentsRefresh(prev => prev + 1);
    }, []);

    return {
        uploadDialogOpen,
        setUploadDialogOpen,
        activeTab,
        setActiveTab,
        attachmentsRefresh,
        refreshAttachments,
        isReasoningExpanded,
        setIsReasoningExpanded,
        toggleReasoningExpanded,
    };
}
