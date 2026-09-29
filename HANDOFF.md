# HANDOFF (caption-batch)

新しいチャットで続きをやるときの短い引き継ぎ。区切りごとに更新する。

## 今の状態（2026-09-29）
- 版: 0.6.1（GitHub `main` とユーザーPC `F:\_AI_tool\caption-batch` で一致、動作OKの報告あり）
- 用途: Gemini（主に Flash Lite）/ OpenRouter で大量画像にキャプション付け。100万枚規模前提
- 起動: `start.bat`、更新: `update.bat`（fetch + reset --hard origin/main、`.env` と `ui-settings.json` は残る）
- ポート: 127.0.0.1:8771。APIキーは `.env`（git管理外）

## 構成
- `src/caption_batch/core/` 処理本体（`run_batch_impl.py`）、プロバイダ別リクエスト
- `src/caption_batch/cli/main.py` CLI
- `web/` WebUI（`app.js` 568行。次に触るとき分割する）
- `tests/` pytest（0.6.1 時点で41件通過）

## 主な機能
前処理（リサイズ/形式/画質）、temperature/top_p/max_tokens/seed、thinking/reasoning、media_resolution、
プレビュー、進捗/ETA/失敗一覧、RPM制限、ジョブスナップショット再開、few-shot、
システム指示（旧prompt欄）＋ユーザー指示（空なら既定）、並び順 Gemini=画像→文 / OpenRouter=文→画像

## 未着手の候補（頼まれたらやる）
safety設定（NSFW拒否対策）、Gemini 2.5 thinkingBudget、OpenRouter reasoning.max_tokens / プロバイダ固定、JSON構造化出力

## 作業ルール
git push で反映、差分だけ編集、検証は触った部分のみ（フルはリリース時）。
