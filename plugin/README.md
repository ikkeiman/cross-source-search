# kintone プラグイン（参照実装）

レコードの追加・編集画面にファイル選択欄を足し、選んだファイルを `cross-source-search` の `POST /attachments` に送って、
返ってきた保存先（パスと URL）をレコードのフィールドに書き戻すプラグインです。ファイルの実体は kintone ではなく
Dropbox 側（開発時はローカルフォルダ）に置かれるので、利用者は Dropbox を意識せずに添付でき、
取り込みパイプラインの検索対象にも自動で入ります。

## 状態

- `POST /attachments`（API 側）は実装・テスト済み
- この JS は **kintone 環境で動作確認していません**。実際に使うには次が必要です
  - 設定画面（`html/config.html`、`js/config.js`）の実装。`apiBaseUrl`、`pathField`、`urlField` を保存する
  - API 側で kintone のドメインからの CORS を許可する
  - `kintone-plugin-packer` でパッケージ化し、署名用の秘密鍵を安全に保管する（リポジトリには入れない）
- アイコン `image/icon.png` は含めていません
