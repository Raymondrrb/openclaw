# Deploy Rayviews Lab Dashboard to Vercel

## Prerequisites

- GitHub repo pushed with the `web/` directory
- Supabase project URL + anon key + service role key

## Steps

### 1. Import project in Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Select the openclaw repository
3. Set **Root Directory** to `web`
4. Set **Framework Preset** to **Next.js**
5. Set **Build Command** to `npm run build`
6. Set **Install Command** to `npm install`

### 2. Add environment variables

Add these in Vercel project settings > Environment Variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Supabase service role key (server only) |

Optional:
| `TELEGRAM_BOT_TOKEN` | Bot token | For future notifications |
| `TELEGRAM_CHAT_ID` | Chat ID | For future notifications |

### 3. Deploy

Click **Deploy**. Vercel will build and deploy automatically.

### 4. Verify

1. Hit `{your-url}/api/health` — all checks should be green
2. Hit `{your-url}/` — shows latest pipeline run (or "No runs yet")
3. Hit `{your-url}/runs` — shows recent runs table

### Subsequent deploys

Every push to `main` triggers automatic deployment.

## Local development

```bash
cd web
cp .env.example .env.local
# Fill in real values in .env.local
npm install
npm run dev
# Open http://localhost:3000
```
