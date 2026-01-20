import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/**
 * Sign in with Google OAuth.
 * This is the only authentication method available.
 */
export async function signInWithGoogle() {
    const { data, error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
            redirectTo: `${window.location.origin}/auth/callback`,
        },
    });

    if (error) {
        throw error;
    }

    return data;
}

/**
 * Sign out the current user.
 */
export async function signOut() {
    const { error } = await supabase.auth.signOut();
    if (error) {
        throw error;
    }
}

/**
 * Get the current session.
 */
export async function getSession() {
    const {
        data: { session },
    } = await supabase.auth.getSession();
    return session;
}

/**
 * Get the current user.
 */
export async function getUser() {
    const {
        data: { user },
    } = await supabase.auth.getUser();
    return user;
}

/**
 * Get the access token for API calls.
 */
export async function getAccessToken(): Promise<string | null> {
    const session = await getSession();
    return session?.access_token ?? null;
}
