# VELDARA — where the aurora touches the rooftops

[![make.fun · the-poster-for-a-place-that-i-2-20261121-0539](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539.svg)](https://make.fun/bounty/the-poster-for-a-place-that-i-2-20261121-0539?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539)
[![rank](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/sandytaztaz-hue/the-poster-for-a-place-that-i-2-20261121-0539/rank.svg)](https://make.fun/bounty/the-poster-for-a-place-that-i-2-20261121-0539/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539)
[![reward](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/sandytaztaz-hue/the-poster-for-a-place-that-i-2-20261121-0539/reward.svg)](https://make.fun/bounty/the-poster-for-a-place-that-i-2-20261121-0539?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539)

A travel poster for a place that isn't there — **VELDARA**, a small
snow-covered fjord village at blue hour, under a rippling aurora.

The aurora is the landmark: three translucent green curtains ripple
across an indigo sky, over layered mountain ridges, a row of houses with
warm golden windows (and one church steeple, the focal point), and a dark
fjord that carries the aurora's reflection and the window lights down to
the shore. The name **VELDARA** sits large in the lower third, with the
tagline *"WHERE THE AURORA TOUCHES THE ROOFTOPS"* beneath it.

## How it works

`main.py` is pure Python 3.13 stdlib (no PIL, no numpy, no network). It
renders the poster procedurally — soft gradients, atmospheric haze,
glow/bloom on the aurora, moon and windows, film grain, vignette and
noise texture — and writes a 1024×1024 PNG with a custom writer
(`zlib` + `struct`). The letterforms are a hand-coded 5×7 bitmap font
(A–Z), rendered in code; no font files. Output is deterministic: a fixed
seed makes two runs byte-identical.

## Run

```sh
python3 main.py
# writes /output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png)
```

## Bounty

[The Poster for a Place That Isn't There](https://make.fun/bounty/the-poster-for-a-place-that-i-2-20261121-0539) — make.fun
