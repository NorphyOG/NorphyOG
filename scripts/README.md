# Profile art

The portfolio uses local, self-contained SVGs inspired by [Avi Vashishta's animated README guide](https://www.avivashishta.com/blog/build-animated-github-profile-readme). Its opening introduces NorphyOG and Scanora; selected work follows before the full public repository directory. The developer terminal remains available in the About section.

Python 3.12 and its standard library are sufficient. Run these commands from the repository root; no packages or personal access token are needed.

## Portfolio graphics

Edit the content in `scripts/generate_static_art.py`, then regenerate the SVGs:

```sh
python3 -B scripts/generate_static_art.py
python3 -B scripts/generate_static_art.py --check
```

The generator produces six illustrations: the portfolio hero, the Scanora banner, two project covers, and two terminal cards. The animations play once and keep a complete final frame. Each SVG includes visible fallback content and a reduced-motion rule. Covers scale with the README width; the terminal cards can wrap onto separate rows on small screens. Project covers explain the tools' workflows rather than depicting application screenshots.

`assets/form-studio-editor.png` is an unchanged copy of the [FORM / STUDIO editor screenshot](https://github.com/NorphyOG/form-studio/blob/main/docs/seiteneditor.png), used to show the actual open-source application. It is independent of the generated profile art.

`assets/form-studio-designs.gif` is an unchanged copy of the [FORM / STUDIO design-switcher capture](https://github.com/NorphyOG/form-studio/blob/main/docs/design-switcher.gif). It shows real design packages in motion and is placed inside an expandable project section; the editor screenshot stays visible in the main portfolio.

## Contribution calendar

```sh
python3 -B scripts/fetch_contributions.py
python3 -B scripts/render_heatmap_svg.py
```

The fetcher reads GitHub's public contribution calendar, matches each day with its exact tooltip count, and checks the date range and displayed total before replacing `data/contributions.json`. The renderer writes `assets/contrib-heatmap.svg` from that data. A failed fetch keeps the existing data, and the workflow stops before committing outputs.

To validate live fetching without changing the saved profile graphics:

```sh
python3 -B scripts/fetch_contributions.py --output /tmp/norphy-contributions.json
python3 -B scripts/render_heatmap_svg.py --input /tmp/norphy-contributions.json --output /tmp/norphy-heatmap.svg
```

## Checks and automation

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/generate_static_art.py --check
git diff --check
```

`.github/workflows/update-profile-art.yml` refreshes the contribution calendar daily, on manual dispatch, and when its pipeline files change on `main`. After these files reach `main`, the workflow uses GitHub's automatically supplied token to commit only the calendar JSON and SVG. No personal token needs to be configured. Static cards stay unchanged until their generator is run deliberately.

Review the project directory when repositories become public, are renamed, or change purpose; the calendar workflow does not alter project descriptions.
