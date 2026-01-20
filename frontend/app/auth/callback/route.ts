import { NextResponse } from "next/server";

export async function GET(request: Request) {
    const requestUrl = new URL(request.url);
    const origin = requestUrl.origin;

    // Supabase handles the OAuth callback automatically
    // This route just redirects to the main page after auth
    return NextResponse.redirect(`${origin}/`);
}
