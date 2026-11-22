# Statute & Precedent — installable study app

Study notebook for the Indian Partnership Act, 1932 and the Sale of Goods Act, 1930:
1,139 recall cards, the Story chain with full section gists, and the Reference index.

## Put it online free with GitHub Pages (about 5 minutes)

1. On GitHub, create a new repository (for example `statute-precedent`). It can be private
   only on a paid plan; on a free plan GitHub Pages needs it to be **public**.
2. Click **Add file → Upload files** and upload everything in this folder, keeping the
   `icons` folder: `index.html`, `manifest.webmanifest`, `sw.js`, `README.md`, `icons/`.
3. Go to **Settings → Pages**. Under "Build and deployment", choose **Deploy from a branch**,
   branch **main**, folder **/ (root)**, and Save.
4. After a minute, your site is live at `https://<your-username>.github.io/statute-precedent/`.

(Netlify Drop also works: drag this whole folder onto https://app.netlify.com/drop.)

## Install it as an app

- **Android (Chrome):** open the site → ⋮ menu → **Install app** / **Add to Home screen**.
- **iPhone / iPad (Safari):** open the site → Share → **Add to Home Screen**.
- **Laptop (Chrome or Edge):** click the install icon at the right end of the address bar.

Open it once while online; after that it works offline. Your progress (mastered cards,
review pile, theme) is saved on each device separately.

## Updating

Replace `index.html` with a new version. To make installed copies refresh straight away,
also change the version name on the first line of `sw.js` (e.g. `statute-precedent-v2`).

## Opening without hosting

You can also just double-click `index.html` to use it in a browser. Offline install needs
the site to be served over https (GitHub Pages / Netlify), not opened as a file.
