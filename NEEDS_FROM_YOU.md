# Inputs needed from you

Fill in whatever sections you want to unblock, save the file, and tell me
"saved" / "updated" — I'll pick up from there. Leave anything blank that
you want to skip for now; I'll just leave that item gated.

---

## 1. Real Supabase migration (chunk 1, Task 11)

Project: `claudeshorts` (nddlutmilajkqtoygmfi)

- **Session Pooler connection string** (Supabase dashboard → Project Settings
  → Database → Connection string → "Session pooler"):
  ```
  SUPABASE_DB_URL=
  ```
- Confirm: OK to back up `data/app.db` and run the migration script against
  the above URL? [X] yes  [ ] wait
1. Install packages
Run this command to install the required dependencies.
Details:
npm install @supabase/supabase-js @supabase/ssr
Code:
File: Code
```
npm install @supabase/supabase-js @supabase/ssr
```

2. Add files
Add env variables, create Supabase client helpers, and set up middleware to keep sessions refreshed.
Code:
File: .env.local
```
NEXT_PUBLIC_SUPABASE_URL=https://nddlutmilajkqtoygmfi.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_NNakJ-k_bBMtpffxjkW5Jw_Dfzn6Pdf
```

File: page.tsx
```
1import { createClient } from '@/utils/supabase/server'
2import { cookies } from 'next/headers'
3
4export default async function Page() {
5  const cookieStore = await cookies()
6  const supabase = createClient(cookieStore)
7
8  const { data: todos } = await supabase.from('todos').select()
9
10  return (
11    <ul>
12      {todos?.map((todo) => (
13        <li key={todo.id}>{todo.name}</li>
14      ))}
15    </ul>
16  )
17}
```

File: utils/supabase/server.ts
```
1import { createServerClient } from "@supabase/ssr";
2import { cookies } from "next/headers";
3
4const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
5const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
6
7export const createClient = (cookieStore: Awaited<ReturnType<typeof cookies>>) => {
8  return createServerClient(
9    supabaseUrl!,
10    supabaseKey!,
11    {
12      cookies: {
13        getAll() {
14          return cookieStore.getAll()
15        },
16        setAll(cookiesToSet) {
17          try {
18            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
19          } catch {
20            // The `setAll` method was called from a Server Component.
21            // This can be ignored if you have middleware refreshing
22            // user sessions.
23          }
24        },
25      },
26    },
27  );
28};
```

File: utils/supabase/client.ts
```
1import { createBrowserClient } from "@supabase/ssr";
2
3const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
4const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
5
6export const createClient = () =>
7  createBrowserClient(
8    supabaseUrl!,
9    supabaseKey!,
10  );
```

File: utils/supabase/middleware.ts
```
1import { createServerClient } from "@supabase/ssr";
2import { type NextRequest, NextResponse } from "next/server";
3
4const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
5const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
6
7export const createClient = (request: NextRequest) => {
8  // Create an unmodified response
9  let supabaseResponse = NextResponse.next({
10    request: {
11      headers: request.headers,
12    },
13  });
14
15  const supabase = createServerClient(
16    supabaseUrl!,
17    supabaseKey!,
18    {
19      cookies: {
20        getAll() {
21          return request.cookies.getAll()
22        },
23        setAll(cookiesToSet) {
24          cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value))
25          supabaseResponse = NextResponse.next({
26            request,
27          })
28          cookiesToSet.forEach(({ name, value, options }) =>
29            supabaseResponse.cookies.set(name, value, options)
30          )
31        },
32      },
33    },
34  );
35
36  return supabaseResponse
37};
```

3. Install Agent Skills (Optional)
Agent Skills give AI coding tools ready-made instructions, scripts, and resources for working with Supabase more accurately and efficiently.
Details:
npx skills add supabase/agent-skills
Code:
File: Code
```
npx skills add supabase/agent-skills
```

---

## 2. Chunk 10 — Publishing plugins (YouTube/TikTok/Instagram API upload)

- Which platform(s) do you want real API publishing for first?
  [ ] YouTube  [ ] TikTok  [ ] Instagram  [x] skip for now (keep folder-export only)

- YouTube Data API credentials (OAuth client JSON from Google Cloud Console):
  ```
  YOUTUBE_API_CREDENTIALS_JSON=
  ```
- TikTok Content Posting API credentials (developer app):
  ```
  TIKTOK_API_CREDENTIALS=
  ```
- Instagram Graph API credentials (Meta developer app):
  ```
  INSTAGRAM_API_CREDENTIALS=
  ```

---

## 3. Chunk 11 — Browser-profile publishing (login-based, no API keys)

Alternative to chunk 10 for platforms without easy API access. For each
platform you want, I'd walk you through an interactive login once
(`scripts/interactive_login.py`) — this just needs your go-ahead, not a
credential pasted here:

- [x] Set up YouTube Studio browser profile
- [x] Set up TikTok browser profile
- [x] Set up Instagram browser profile

---

## 4. Chunk 12 — Telegram bot (remote approve/generate control)

- Bot token (from @BotFather on Telegram — `/newbot`, then paste the token):
  ```
  TELEGRAM_BOT_TOKEN=8908735537:AAGBrbdPoEBQ4NTmW__b4rx5dBvIwkBAWPM
  ```
- Your Telegram chat ID (so the bot only responds to you — get it from
  @userinfobot or similar):
  ```
  TELEGRAM_CHAT_ID=5911407029
  ```

---

## 5. Chunk 13 — Higgsfield / Google Veo video generation

Research-only chunk, no build yet — just a decision for later:

- [ x ] Use Google AI Pro subscription ($20/mo, ~3 Veo clips/day via Flow, no
      extra API cost)
- [ ] Use Vertex AI API key directly (pay-per-second, $0.15–$0.40/sec)
- [ ] Skip Veo/Higgsfield for now

---

## 6. Chunk 14 — Additional LLM provider (for the openai_compat backend)

Pick one vendor (or skip to keep using claude_cli/api only):

- [ x ] OpenRouter — base_url `https://openrouter.ai/api/v1`
- [ ] NVIDIA NIM — base_url `https://integrate.api.nvidia.com/v1`
- [ ] Gemini — base_url `https://generativelanguage.googleapis.com/v1beta/openai/`
- [ ] skip

```
OPENAI_COMPAT_API_KEY=<set in .env, not duplicated here>
```
Model name to use (vendor-specific, e.g. `openai/gpt-4o-mini` for
OpenRouter, `meta/llama-3.1-70b-instruct` for NIM, `gemini-2.0-flash` for
Gemini):
```
model name: openai/gpt-oss-120b:free
(picked over other free models because it has native OpenAI-style function/tool-calling
trained in, 131K context, and strong instruction-following; fallback if rate-limited
(20 req/min, 200 req/day): google/gemma-4-31b:free)
```

---

That's everything currently gated on you. Chunks 1-8 (core platform
rebuild) continue in the background regardless of this file.
