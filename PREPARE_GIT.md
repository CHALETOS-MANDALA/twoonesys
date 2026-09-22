# Prima del `git push` su GitHub

`gh` deve essere loggato (`gh auth login`). Oggi non lo è.

## 1. Un solo git (CASCADE dentro TWOONESYS)

`harness/` ha un `.git` nested (storia CASCADE locale). GitHub padre non può
tracciare i file finché quella cartella è un altro repo.

Una volta, dalla root TWOONESYS:

```text
ren harness\.git harness\.git.cascade-local
```

La storia CASCADE resta sul disco, non va sul remote. Poi:

```text
git add README.md LICENSE NOTICE PREPARE_GIT.md docs .gitignore
git add harness pct bridge engine
git status
```

Controlla che **non** compaiano: `run_six`, `receipts_*`, `sandbox_*`,
`engine/models`, `.venv`, `signing_key`, `.env`.

## 2. Commit (quando Rubinho lo chiede)

Messaggio tipo: `Prepare TWOONESYS for public GitHub (CASCADE + PCT + gate).`

## 3. Remote

```text
gh auth login
gh repo create twoonesys --public --source=. --remote=origin --push
```

Non usare `--push` se lo status è sporco o se `harness/` è ancora un gitlink.
