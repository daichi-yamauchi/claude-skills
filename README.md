# daichi-skills

個人用の Claude Code スキルを、ローカルとクラウドのセッションの両方から同じ形で使うための marketplace。

`~/.claude/skills/` に置いた個人スキルはクラウドのセッションに同期されない (同期されるのは marketplace の登録情報だけ)。
そこでスキル本体をこのリポジトリに置き、marketplace として登録して配る。

## 使う側の手順

```bash
# 1 回だけ: marketplace を登録する (登録情報は環境をまたいで同期される)
claude plugin marketplace add daichi-yamauchi/claude-skills

# 使いたいスキルを入れる
claude plugin install akapen@daichi-skills
```

対話中なら `/plugin marketplace add daichi-yamauchi/claude-skills` と `/plugin install akapen@daichi-skills` でも同じ。

## 中身

| プラグイン | 中身 |
|---|---|
| `akapen` | 実装前の赤ペン先生。ラウンド制の問い出し、図 DSL から HTML シートを生成する `build.py`、指摘 / 添削モード |

## 更新のしかた

**このリポジトリが正本。** ローカルの `~/.claude/skills/akapen` はここへの symlink なので、
どちらを編集しても同じファイルを触っている。コピーや rsync は不要。

```bash
claude plugin validate .                     # manifest と skills の検査
git add skills/akapen/...                    # 触ったファイルを個別に指定する
git commit && git push
claude plugin update akapen@daichi-skills    # 使っている側 (クラウド等) で取り込む
```

ローカルには `claude plugin install` しない。symlink 経由で既に見えているので、入れると二重になる。

## 見本について

`skills/akapen/assets/example/` の 2 つはどちらも公開前提。

| ファイル | 中身 |
|---|---|
| `part4-01.akapen.md` | 図 DSL をひと通り使った見本 (全体図・A/B 図・時間軸・問い 3 つ)。題材は匿名化済み |
| `smoke-01.akapen.md` | 架空の題材。`build.py` と公開経路の動作確認用 |
