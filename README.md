# Las Olas Yacht Management — review website

Public desktop and mobile design preview: https://grandpajackai.github.io/las-olas-yacht-management/

This static review site uses original editorial copy, a deep teal / ivory / gold visual system, self-hosted fonts, and a scroll-driven yacht journey. It contains 23 main pages, a custom 404, service and program detail pages, a journal, and an inquiry brief generator.

## Editing and publishing

- `build.py` generates HTML, metadata, the sitemap, and robots.txt into `docs/`.
- `content.json` holds service and proposed management program content.
- `journal.json` holds the ownership articles.
- `docs/assets/site.css` and `docs/assets/site.js` contain the visual system and interactions. Edit these files directly; the generator preserves them.
- GitHub Pages publishes `main` → `/docs`. Push regenerated pages after changes.

```sh
python3 build.py
python3 scripts/check-site.py
node --check docs/assets/site.js
```

The default site URL includes the GitHub repository prefix. To prepare a different domain, set `SITE_URL` when running the generator. `REVIEW_PREVIEW=0` removes the preview's search-engine noindex setting for a confirmed production launch. Public review does not require sign-in; noindex is a search-engine instruction, not access control.

## Review scope

The inquiry form creates a text brief locally and offers download and clipboard actions. It **does not send messages or deliver leads**. Contact delivery, verified business details, final program commitments, and a production privacy policy are still needed for a business launch.

The clean text wordmark follows the supplied brand reference. Illustrative yacht images were created with OpenAI ImageGen for this design and do not depict actual clients, projects, or a company fleet. Cormorant Garamond and DM Sans are self-hosted, with their license files in `docs/assets/`.

No website analytics, advertising trackers, remote fonts, or persistent inquiry storage are added. This repository contains only the website source and public review assets; it excludes the original hosting configuration and unrelated project files.
