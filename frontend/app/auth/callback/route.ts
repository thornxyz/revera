import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { cookies } from 'next/headers'

export async function GET(request: Request) {
    const { searchParams, origin } = new URL(request.url)
    const code = searchParams.get('code')
    // if "next" is in param, use it as the redirect URL
    let next = searchParams.get('next') ?? '/'
    if (!next.startsWith('/')) {
        // if "next" is not a relative URL, use the default
        next = '/'
    }

    if (code) {
        const supabase = await createClient()
        const { data, error } = await supabase.auth.exchangeCodeForSession(code)

        console.log('Auth callback - code exchange result:', {
            hasData: !!data,
            hasSession: !!data?.session,
            hasUser: !!data?.user,
            error
        })

        if (!error && data?.session) {
            const forwardedHost = request.headers.get('x-forwarded-host')
            const isLocalEnv = process.env.NODE_ENV === 'development'

            // Create redirect response
            const redirectUrl = isLocalEnv
                ? `${origin}${next}`
                : forwardedHost
                    ? `https://${forwardedHost}${next}`
                    : `${origin}${next}`

            const response = NextResponse.redirect(redirectUrl)

            // Manually set the auth session cookies
            const cookieStore = await cookies()

            // Set the session cookies that Supabase needs
            response.cookies.set({
                name: `sb-${process.env.NEXT_PUBLIC_SUPABASE_URL!.split('//')[1].split('.')[0]}-auth-token`,
                value: JSON.stringify({
                    access_token: data.session.access_token,
                    refresh_token: data.session.refresh_token,
                    expires_at: data.session.expires_at,
                    expires_in: data.session.expires_in,
                    token_type: data.session.token_type,
                    user: data.session.user
                }),
                path: '/',
                maxAge: 60 * 60 * 24 * 7, // 7 days
                httpOnly: false,
                secure: !isLocalEnv,
                sameSite: 'lax'
            })

            console.log('Session cookies set on response')

            return response
        }

        // Log error for debugging
        console.error('Auth callback error or no session:', error)
    }

    // return the user to an error page with instructions
    return NextResponse.redirect(`${origin}/auth/auth-code-error`)
}