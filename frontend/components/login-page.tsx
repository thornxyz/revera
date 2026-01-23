"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { FcGoogle } from "react-icons/fc";

export function LoginPage() {
    const { signIn, loading } = useAuth();

    return (
        <div className="relative min-h-screen bg-linear-to-br from-slate-50 via-white to-emerald-50 flex items-center justify-center px-4 py-10">
            <div className="absolute inset-0 overflow-hidden">
                <div className="absolute -top-32 right-10 h-72 w-72 rounded-full bg-emerald-200/40 blur-3xl" />
                <div className="absolute -bottom-28 left-12 h-72 w-72 rounded-full bg-sky-200/40 blur-3xl" />
            </div>

            <Card className="relative w-full max-w-md bg-white/90 border-slate-200 shadow-xl shadow-emerald-100">
                <CardHeader className="text-center space-y-3">
                    <span className="mx-auto inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                        Research Workspace
                    </span>
                    <div className="text-4xl">🔬</div>
                    <div className="space-y-2">
                        <CardTitle className="text-2xl font-bold bg-linear-to-r from-emerald-600 to-sky-500 bg-clip-text text-transparent">
                            Revera
                        </CardTitle>
                        <p className="text-slate-500 text-sm">
                            Multi-Agent research with transparent citations.
                        </p>
                    </div>
                </CardHeader>
                <CardContent className="space-y-5">
                    <Button
                        onClick={signIn}
                        disabled={loading}
                        className="w-full bg-white text-slate-700 font-medium h-12 flex cursor-pointer items-center justify-center gap-3 border-2 border-slate-400 hover:bg-slate-100 hover:text-slate-900"
                    >
                        <span className="flex items-center justify-center h-9 w-9 rounded-full text-slate-900">
                            <FcGoogle />
                        </span>
                        {loading ? "Signing in..." : "Continue with Google"}
                    </Button>
                </CardContent>
            </Card>
        </div>
    );
}
