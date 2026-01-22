import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function createClient() {
    const cookieStore = await cookies()

    return createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
            cookies: {
                getAll() {
                    return cookieStore.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        try {
                            cookieStore.set(name, value, options)
                        } catch (error) {
                            // The `set` method was called from a Server Component or 
                            // middleware where cookie setting may fail.
                            // In Route Handlers, this should work fine.
                            // If this fails in a Route Handler, check your Next.js version.
                        }
                    })
                },
            },
        }
    )
}