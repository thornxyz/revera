"use client";

import { AuthProvider } from "@/lib/auth-context";
import { Toaster } from "sonner";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <Toaster position="top-right" richColors />
            {children}
        </AuthProvider>
    );
}
