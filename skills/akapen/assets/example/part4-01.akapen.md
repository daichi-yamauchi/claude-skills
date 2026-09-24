---
label: part4-01
date: 2026-09-14
round: 1
title: PV と Cookie はサイト Worker の中で完結させる
reader: Claude Code を使う開発者。説明なしで使ってよい語は Worker / D1 / Cron / Cookie
source: packages/site-worker と packages/lp-api のコード、および打ち合わせメモから
---

結論: PV の記録と Cookie の発行はサイト Worker だけで済ませる。中央（lp-api・D1）が出てくるのは夜の集計と stats の応答だけ。決めたいのは配信元・日付の境界・プレビューでの復元の 3 点。

用語:
- AE — Cloudflare Analytics Engine。生の計測点を溜める場所
- tv — 計測スクリプトの版番号。変わるまでブラウザがキャッシュを使い続ける

```fig overview
title: PV と Cookie はサイト Worker の中で完結。中央が出てくるのは夜の集計と stats の応答だけ
caption: 図 1 — 何を見るか: 赤い箱が部品 4 で作るところ。① は t.js をどこから配るか（問 1）、② は「1 日」をどの時刻で切るか（問 2）、③ はプレビューで遅延タグを復元するか（問 3）
node browser 16 40 170 | 閲覧者のブラウザ
  GET /（HTML）
  GET /__lp/t.js（2KB）
  POST /__lp/e（操作・到達）
  GET /__lp/x?t=（自己除外）
  !③ プレビューでは遅延タグを復元しない？
node worker 228 40 236 red | サイト Worker（部品 4 で足すところ）
  HTML 200 のとき: 除外の印を決める → Cookie 3 本
  → AE に PV を 1 点（待たせない）
  /__lp/e: 点を書き、訪問 Cookie を延ばす
  /__lp/t.js: 束ねた計測スクリプトを返す
  /__lp/x: 自己除外の Cookie を置く
node ae 506 40 198 | Analytics Engine（生の点）
  dataset 1 つ・index = siteId
  blob: 種別・版・path・ホスト種別・除外・訪問・訪問者・参照元・UTM・クリック ID の種別・端末・国・section
  保持 3 か月（公式）
node stats 16 202 232 red | GET /v1/sites/{id}/stats
  畳んだ日 → D1、まだの日（今日）→ AE を直接
  pv・noInteractionPv・除外の内訳・到達
node d1 290 202 172 | D1 stats_daily
  日 × 版 × 種別 × キー × 除外
  !② 「1 日」の境界は日本時間？
node cron 506 202 198 red | lp-api の Cron（毎晩）
  直近 3 日分を SQL で集計し直す
  （1 回落ちても次で埋まる）
node loader 16 284 688 | 部品 3 の遅延ローダー（HTML に焼き込み済み）との接点
  復元関数の先頭に 1 行: 自己除外の Cookie（JS から読める形にする）があれば復元しない
edge browser:r -> worker:l
edge worker:r -> ae:l
edge ae:b -> cron:t
edge cron:l -> d1:r
edge d1:l -> stats:r
edge stats:t -> ae:b:0.27 dashed "今日の分は AE に SQL を 1 回"
mark 1 browser 156 54
mark 3 browser 156 12
mark 2 cron 186 10
```

## 計測スクリプトは同一オリジンで配る

サイト Worker が t.js を返せば、ブラウザから見て DNS と TLS の接続は 1 本で済む。代わりに t.js を更新するにはサイトのビルドを作り直す必要がある。==lp-api から配る案== は更新が楽だが、サイトごとに別オリジンへの接続が 1 本増える。

```fig ab-1a w=360 fs=10.5
title: A. サイト Worker に束ねる
caption: A — 接続は 1 本のまま。更新はビルドの作り直し
node site 8 26 200 | example.com
  `GET /__lp/t.js`
node w 8 84 200 red | サイト Worker が返す
  1 年キャッシュ（tv が変わるまで再取得なし）
edge site:b -> w:t
```

```fig ab-1b w=360 fs=10.5
title: B. lp-api から配る
caption: B — 更新は lp-api のデプロイだけ。接続が 1 本増える
node site 8 26 200 | example.com
  `GET https://t.lp.example-cdn.net/t.js`
node api 8 84 200 red | lp-api（別オリジン）
  DNS ＋ TLS がもう 1 本
edge site:b -> api:t
```

| 案 | 更新のしやすさ | ブラウザの接続数 |
|---|---|---|
| A. サイト Worker に束ねる | ビルドの作り直し（ローダーと同じ扱い） | 1 本のまま |
| B. lp-api から配る | lp-api のデプロイだけ（全サイトに即時） | 別オリジンが 1 本増える |

```q
問 1. 計測スクリプト t.js をどこから配るか
A* サイト Worker に束ねる | 利点: 接続 1 本のまま、プレビューでも同じ経路 | 代償: 更新はビルドの作り直し | fig: ab-1a
B  lp-api から配る | 利点: 更新は lp-api のデプロイだけで全サイトに即時 | 代償: DNS + TLS がもう 1 本、ブロッカーに掛かりやすい | fig: ab-1b
根拠: packages/site-worker/src/index.ts:88 で HTML 応答に Set-Cookie を付けている。t.js は 2KB
```

## 「1 日」は日本時間で切る

```fig ab-2a w=360 fs=10.5
title: A. 日本時間 0:00 で切る
caption: A — GA4（JST）の日別と同じ日に入る
axis 12 70 340
vline 176 44 92 red
note c 140 28 80 | !JST 0:00
dot 60 70
dot 100 70
dot 150 70
dot 210 70
note d1 20 78 60 | 9/1
note d2 300 78 60 | 9/2
note e 190 96 150 | JST 8:00 の PV → 9/2 に入る
```

```fig ab-2b w=360 fs=10.5
title: B. UTC 0:00（日本時間 9:00）で切る
caption: B — SQL はそのまま。朝 8 時の PV が前日に入る
axis 12 70 340
vline 230 44 92 red
note c 186 28 90 | !JST 9:00 = UTC 0:00
dot 60 70
dot 100 70
dot 150 70
dot 210 70
note d1 20 78 60 | 9/1
note d2 300 78 60 | 9/2
note e 120 96 150 | !JST 8:00 の PV → 9/1 に入る
```

```q
問 2. 夜の集計で「1 日」をどの時刻で切るか
A* 日本時間 0:00 | 利点: 管理画面の「今日」と一致する | 代償: Cron の SQL で 9 時間ずらす | fig: ab-2a
B  UTC 0:00（日本時間 9:00） | 利点: SQL がそのまま | 代償: 朝 8 時の PV が前日に入る | fig: ab-2b
根拠: packages/lp-api/src/cron.ts:41 は現在 UTC の date() で集計している
```

```q
問 3. プレビュー URL では遅延タグ（GA4・Pixel）を復元しないか
A* 復元しない | 利点: 先方の GA4 にプレビューの PV が混ざらない | 代償: プレビューでタグの動作を目で確認できない
B  復元する | 利点: 本番と同じ挙動を確認できる | 代償: 先方の GA4 / Pixel に PageView が載る
根拠: packages/site-worker/src/loader.ts:12 の復元関数は現在ホスト名を見ていない
```

```details 検討して落とした 2 案（各 2 行）
- Durable Object で集計: 1 サイト 1 DO で常時集計。落とした理由は費用と、D1 の集計と二重管理になること
- AE を使わず D1 に直接書く: 書き込み回数が PV 数に比例し、無料枠を 1 サイトで使い切る
```
