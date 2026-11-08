/*
 * kintone プラグインの参照実装（デスクトップ側）。
 *
 * 動き: レコードの追加・編集画面にファイル選択欄を出し、選ばれたファイルを
 * cross-source-search の POST /attachments に送る。返ってきた path と url を、
 * プラグイン設定で指定したフィールド（pathField / urlField）に入れる。
 * ファイルの実体は kintone に置かず、Dropbox 側に置く。
 *
 * 注意: この JS は kintone 環境で動作確認していない。API 側（/attachments）はテスト済み。
 *       実際に使うときは kintone.plugin.app.getConfig の値と、CORS（API 側で kintone のドメインを許可）が必要。
 */
(function (PLUGIN_ID) {
  'use strict';
  const config = kintone.plugin.app.getConfig(PLUGIN_ID) || {};
  const apiBaseUrl = (config.apiBaseUrl || '').replace(/\/$/, '');
  const pathField = config.pathField;
  const urlField = config.urlField;

  function mount(event) {
    const space = kintone.app.record.getHeaderMenuSpaceElement();
    if (!space || space.querySelector('.xsearch-upload')) return event;
    const wrap = document.createElement('div');
    wrap.className = 'xsearch-upload';
    wrap.innerHTML = '<label>外部ストレージへ添付: <input type="file"></label><span class="xsearch-status"></span>';
    const input = wrap.querySelector('input');
    const status = wrap.querySelector('.xsearch-status');
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const rec = kintone.app.record.get();
      const recordId = (rec.record.$id && rec.record.$id.value) || 'new';
      const form = new FormData();
      form.append('app_id', String(kintone.app.getId()));
      form.append('record_id', String(recordId));
      form.append('file', file, file.name);
      status.textContent = '保存中…';
      try {
        const res = await fetch(apiBaseUrl + '/attachments', { method: 'POST', body: form });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const saved = await res.json();
        const current = kintone.app.record.get();
        if (pathField && current.record[pathField]) current.record[pathField].value = saved.path;
        if (urlField && current.record[urlField]) current.record[urlField].value = saved.url;
        kintone.app.record.set(current);
        status.textContent = '保存しました: ' + saved.path;
      } catch (e) {
        status.textContent = '保存に失敗しました（' + e.message + '）';
      }
    });
    space.appendChild(wrap);
    return event;
  }

  kintone.events.on(['app.record.create.show', 'app.record.edit.show'], mount);
})(kintone.$PLUGIN_ID);
