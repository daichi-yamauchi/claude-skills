/* ===== akapen 回答フォーム (build.py が埋め込む固定 JS)。QUESTIONS / DRAFT_KEY / DOC は build が先頭で定義する =====
   回答の形は references/reply-format.md。選択肢: 択一 / 未選択 (= お任せ) / 保留 (聞きたいことがある) */
function saveDraft() {
  try {
    var d = {};
    document.querySelectorAll("main input[type=radio]:checked").forEach(function (el) { d[el.name] = el.value; });
    document.querySelectorAll("main textarea").forEach(function (el) { if (el.id !== "out" && el.name && el.value) d[el.name] = el.value; });
    localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  } catch (e) {}
}
function loadDraft() {
  try {
    var d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}");
    Object.keys(d).forEach(function (k) {
      try {
        if (!/_(note|hold)$/.test(k) && k !== "global_note" && /^[A-Za-z0-9]+$/.test(String(d[k]))) {
          var r = document.querySelector('main input[name="' + k + '"][value="' + d[k] + '"]');
          if (r) { r.checked = true; return; }
        }
        var t = document.querySelector('main textarea[name="' + k + '"]');
        if (t) t.value = d[k];
      } catch (e) {}
    });
  } catch (e) {}
}
var formEl = document.querySelector("main");
if (formEl) { formEl.addEventListener("change", saveDraft); formEl.addEventListener("input", saveDraft); }
document.querySelectorAll(".qcard[data-qid]").forEach(function (q) {
  var radios = q.querySelectorAll("input[type=radio]");
  if (!radios.length) return;
  var a = document.createElement("a");
  a.textContent = "選択を解除 (お任せに戻す)";
  a.className = "clearsel";
  a.onclick = function () { radios.forEach(function (r) { r.checked = false; }); saveDraft(); };
  q.appendChild(a);
});
function oneLine(s) { return s.trim().replace(/\s*\n\s*/g, " "); }
function buildPrompt() {
  var lines = ["【赤ペン回答】" + DOC];
  Object.keys(QUESTIONS).forEach(function (qid) {
    var choiceEl = document.querySelector('main input[name="' + qid + '"]:checked');
    var noteEl = document.querySelector('main textarea[name="' + qid + '_note"]');
    var holdEl = document.querySelector('main textarea[name="' + qid + '_hold"]');
    var note = noteEl ? noteEl.value.trim() : "";
    var line = QUESTIONS[qid] + ": ";
    if (choiceEl && choiceEl.value === "hold") {
      var hv = holdEl ? holdEl.value.trim() : "";
      line += "(保留) 質問: " + (hv ? oneLine(hv) : "(未記入 — 何を聞きたいか次の返信で)");
    } else if (choiceEl) {
      var lab = choiceEl.closest("label");
      var b = lab ? lab.querySelector("b") : null;
      var lbl = b ? b.innerText.trim() : "";
      lbl = lbl.replace(new RegExp("^" + choiceEl.value + "[.．]\\s*"), "");
      line += choiceEl.value + " — " + (lbl || choiceEl.value);
    } else {
      line += "(未選択 = お任せ)";
    }
    if (note) line += " / 補足: " + oneLine(note);
    lines.push(line);
  });
  var g = document.querySelector('main textarea[name="global_note"]');
  var gv = g ? g.value.trim() : "";
  lines.push("全体への赤ペン: " + (gv || "(なし)"));
  lines.push("---");
  lines.push("上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定し、保留の項目は質問に答えてから次の往復で再確認してください。");
  return lines.join("\n");
}
function generatePrompt() { copyPrompt(buildPrompt(), ""); }
function copyPrompt(text, prefix) {
  var out = document.getElementById("out");
  out.style.display = "block";
  out.value = text;
  var done = function (copied) {
    // 自動コピーは環境により拒否される (ホストされたページの iframe、古いブラウザ)。
    // 失敗したら本文を選択状態にして、長押し / 右クリックでそのままコピーできるようにする
    if (!copied) { try { out.focus(); out.select(); out.setSelectionRange(0, out.value.length); } catch (e) {} }
    setStatus(prefix + (copied ? "✓ コピーしました — Claude Code に貼り付けて Enter"
                                : "下の文章を選んであります。そのままコピーして Claude Code に貼り付けてください"), copied ? "ok" : "err");
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
  } else {
    try { out.select(); done(document.execCommand("copy")); } catch (e) { done(false); }
  }
}
function setStatus(msg, cls) { var el = document.getElementById("status"); el.textContent = msg; el.className = "status " + cls; }
loadDraft();
