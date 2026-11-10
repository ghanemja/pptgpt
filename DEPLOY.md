# Deploy

pptgpt runs on your own computer: see [SETUP.md](SETUP.md) and start it with
`scripts/start.sh`. There is no hosted backend and no login. The server binds
to 127.0.0.1, so only the machine it runs on can open it. Do not put it on a
network or the internet: anyone who could reach it could read and change
every deck and kit on it.

## Static demo on Netlify (optional)

The frontend can also be published as a static site with no server behind
it. Slides then come from the in-browser demo backend, not the engine.

- `netlify-dist/` is **build output, not source**: it is gitignored and
  rebuilt from `frontend/` on every deploy by `scripts/build-netlify.mjs`.
  Edit `frontend/`. A page that references a file the build does not copy
  fails the build rather than publishing a blank page.
- Build settings come from `netlify.toml` (publish: `netlify-dist`,
  command: `node scripts/build-netlify.mjs && node scripts/gen-config.mjs`).
- `BU_API_BASE` stays unset for the static demo.

To preview exactly what Netlify will publish:

```bash
node scripts/build-netlify.mjs && node scripts/gen-config.mjs
python3 -m http.server 8005 --directory netlify-dist
# open http://localhost:8005/workspace.html
```
